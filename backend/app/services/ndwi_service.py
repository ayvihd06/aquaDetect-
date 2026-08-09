"""
NDWI Service
============

Handles:
1. Raster band inspection (reads GeoTIFF metadata to identify spectral bands)
2. NDWI calculation from Green and NIR bands
3. Water mask generation and noise cleaning
4. Polygonization of detected water bodies
5. Statistic calculation
"""

import io
import logging
import math

import numpy as np
import rasterio
from rasterio.features import shapes
from scipy.ndimage import binary_opening, label
from shapely.geometry import shape, mapping
from shapely.validation import make_valid


logger = logging.getLogger(__name__)


# =========================================================
# CONSTANTS
# =========================================================

MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB

# Sentinel-2 band identifiers
S2_GREEN_NAMES = {"b3", "green", "band3", "band_3", "s2_b3"}
S2_NIR_NAMES   = {"b8", "nir", "band8", "band_8", "s2_b8", "nir_broad", "b8a"}

# Minimum connected-pixel area to keep (removes tiny noise specks)
# Expressed in pixels — configurable
DEFAULT_MIN_PIXELS = 10

# Geometry simplification tolerance (degrees) for browser performance
SIMPLIFY_TOLERANCE = 0.00005


# =========================================================
# BAND INSPECTION
# =========================================================

def inspect_raster_bands(file_bytes: bytes) -> dict:
    """
    Open a GeoTIFF and return information about each band.

    Returns
    -------
    dict with keys:
        band_count   : int
        bands        : list of { index: int (1-based), description: str|None, color_interp: str }
        auto_green   : int|None  — 1-based band index if Green detected
        auto_nir     : int|None  — 1-based band index if NIR detected
        auto_detected: bool
        crs          : str|None
        transform    : list|None
    """
    try:
        with rasterio.open(io.BytesIO(file_bytes)) as src:
            band_count = src.count
            bands_info = []

            auto_green = None
            auto_nir   = None

            for i in range(1, band_count + 1):
                desc = src.descriptions[i - 1] or ""
                color_interp = str(src.colorinterp[i - 1].name)

                bands_info.append({
                    "index":        i,
                    "description":  desc if desc else None,
                    "color_interp": color_interp,
                })

                # ----- Try to identify Green band -----
                desc_lower = desc.strip().lower()

                # Substring match: catches "B3 / Green", "B3_green", "Green (B3)", etc.
                is_green = (
                    "b3" in desc_lower
                    or "green" in desc_lower
                    or color_interp.lower() == "green"
                )
                if auto_green is None and is_green:
                    auto_green = i

                # ----- Try to identify NIR band -----
                # Substring match: catches "B8 / NIR", "B8_NIR", "nir_broad", etc.
                # "b8a" is the Red-Edge4 / NIR narrow band — also acceptable as NIR
                is_nir = (
                    "b8" in desc_lower      # catches b8 and b8a
                    or "nir" in desc_lower
                    or color_interp.lower() == "nir"
                )
                # Exclude "b8a" from taking priority over "b8" if both exist
                # (we prefer the broader NIR B8 over B8A, but either works)
                if auto_nir is None and is_nir:
                    auto_nir = i

            auto_detected = (auto_green is not None) and (auto_nir is not None)

            crs_str = str(src.crs) if src.crs else None
            transform_list = list(src.transform) if src.transform else None

            return {
                "band_count":    band_count,
                "bands":         bands_info,
                "auto_green":    auto_green,
                "auto_nir":      auto_nir,
                "auto_detected": auto_detected,
                "crs":           crs_str,
                "transform":     transform_list,
            }

    except rasterio.errors.RasterioIOError as err:
        logger.error("Rasterio could not open the file: %s", err)
        raise ValueError(
            "Invalid satellite image. Please upload a valid multispectral GeoTIFF."
        )
    except Exception as err:
        logger.error("Band inspection failed: %s", err)
        raise ValueError(
            f"Could not inspect the uploaded image: {err}"
        )


# =========================================================
# NDWI PROCESSING
# =========================================================

def process_ndwi_image(
    file_bytes: bytes,
    threshold: float,
    green_band: int,
    nir_band: int,
    min_pixels: int = DEFAULT_MIN_PIXELS,
) -> dict:
    """
    Full NDWI water-detection pipeline.

    Parameters
    ----------
    file_bytes  : Raw bytes of the uploaded GeoTIFF
    threshold   : NDWI threshold for water classification (e.g. 0.30)
    green_band  : 1-based band index for the Green spectral band
    nir_band    : 1-based band index for the NIR spectral band
    min_pixels  : Minimum connected-pixel count to keep (noise removal)

    Returns
    -------
    dict with keys:
        success          : bool
        detection_method : str
        ndwi_threshold   : float
        statistics       : dict
        geojson          : GeoJSON FeatureCollection
    """

    logger.info(
        "NDWI processing started — green_band=%d, nir_band=%d, threshold=%.2f",
        green_band, nir_band, threshold,
    )

    try:
        with rasterio.open(io.BytesIO(file_bytes)) as src:

            # ----------------------------------------------------------
            # Validate band indices
            # ----------------------------------------------------------
            if green_band < 1 or green_band > src.count:
                raise ValueError(
                    f"Green band index {green_band} is out of range "
                    f"(file has {src.count} band(s))."
                )
            if nir_band < 1 or nir_band > src.count:
                raise ValueError(
                    f"NIR band index {nir_band} is out of range "
                    f"(file has {src.count} band(s))."
                )
            if green_band == nir_band:
                raise ValueError(
                    "Green band and NIR band must be different bands."
                )

            # ----------------------------------------------------------
            # Read bands as float32
            # ----------------------------------------------------------
            green = src.read(green_band).astype(np.float32)
            nir   = src.read(nir_band).astype(np.float32)

            nodata = src.nodata
            transform = src.transform
            crs = src.crs

            # ----------------------------------------------------------
            # Build nodata/invalid mask  (True = invalid pixel)
            # ----------------------------------------------------------
            invalid_mask = np.zeros(green.shape, dtype=bool)

            if nodata is not None:
                invalid_mask |= (green == nodata)
                invalid_mask |= (nir   == nodata)

            # Pixels with NaN or Inf
            invalid_mask |= ~np.isfinite(green)
            invalid_mask |= ~np.isfinite(nir)

            # ----------------------------------------------------------
            # NDWI = (Green - NIR) / (Green + NIR)
            # Safe division: avoid zero denominator
            # ----------------------------------------------------------
            denominator = green + nir
            safe_denom  = np.where(
                np.abs(denominator) < 1e-6,
                np.nan,
                denominator,
            )

            ndwi = np.where(
                invalid_mask,
                np.nan,
                (green - nir) / safe_denom,
            )

            logger.info(
                "NDWI range: min=%.4f, max=%.4f (ignoring NaN)",
                float(np.nanmin(ndwi)),
                float(np.nanmax(ndwi)),
            )

            # ----------------------------------------------------------
            # Water mask: NDWI >= threshold  AND  valid pixel
            # ----------------------------------------------------------
            water_mask = (
                np.isfinite(ndwi)
                & ~invalid_mask
                & (ndwi >= threshold)
            ).astype(np.uint8)

            water_pixels_raw = int(water_mask.sum())
            logger.info("Water pixels before cleaning: %d", water_pixels_raw)

            if water_pixels_raw == 0:
                return {
                    "success":          True,
                    "detection_method": "NDWI",
                    "ndwi_threshold":   threshold,
                    "statistics": {
                        "water_body_count":       0,
                        "total_water_area_km2":   0.0,
                        "largest_water_body_km2": 0.0,
                        "average_water_body_km2": 0.0,
                    },
                    "geojson": {
                        "type":     "FeatureCollection",
                        "features": [],
                    },
                }

            # ----------------------------------------------------------
            # Noise cleaning — morphological opening (3×3 kernel)
            # Removes isolated specks while preserving real water bodies
            # ----------------------------------------------------------
            cleaned_mask = binary_opening(
                water_mask.astype(bool),
                structure=np.ones((3, 3)),
            ).astype(np.uint8)

            # ----------------------------------------------------------
            # Connected-component labelling — remove tiny regions
            # ----------------------------------------------------------
            labelled, num_features = label(cleaned_mask)
            logger.info("Connected components before size filter: %d", num_features)

            # Count pixels per label and build a keep-mask
            component_sizes = np.bincount(labelled.ravel())
            # component_sizes[0] = background (skip)
            keep_labels = set(
                idx for idx, count in enumerate(component_sizes)
                if idx > 0 and count >= min_pixels
            )

            final_mask = np.isin(labelled, list(keep_labels)).astype(np.uint8)

            water_pixels_final = int(final_mask.sum())
            logger.info(
                "Water pixels after cleaning: %d (components kept: %d)",
                water_pixels_final, len(keep_labels),
            )

            if water_pixels_final == 0:
                return {
                    "success":          True,
                    "detection_method": "NDWI",
                    "ndwi_threshold":   threshold,
                    "statistics": {
                        "water_body_count":       0,
                        "total_water_area_km2":   0.0,
                        "largest_water_body_km2": 0.0,
                        "average_water_body_km2": 0.0,
                    },
                    "geojson": {
                        "type":     "FeatureCollection",
                        "features": [],
                    },
                }

            # ----------------------------------------------------------
            # Pixel area in m² (from transform)
            # ----------------------------------------------------------
            pixel_width_m  = abs(transform.a)
            pixel_height_m = abs(transform.e)
            pixel_area_m2  = pixel_width_m * pixel_height_m

            # ----------------------------------------------------------
            # Polygonize with rasterio.features.shapes
            # ----------------------------------------------------------
            features = []
            areas_m2 = []

            for geom_dict, value in shapes(
                final_mask,
                mask=final_mask,
                transform=transform,
            ):
                if value == 0:
                    continue

                geom = shape(geom_dict)

                # Make geometry valid (handles self-intersections)
                geom = make_valid(geom)

                if geom.is_empty:
                    continue

                # Simplify for browser performance
                geom_simplified = geom.simplify(
                    SIMPLIFY_TOLERANCE,
                    preserve_topology=True,
                )

                if geom_simplified.is_empty:
                    geom_simplified = geom

                # Area in m²
                area_m2 = geom.area  # shapely area in CRS units

                # If CRS is geographic (degrees), compute approximate area
                if crs and crs.is_geographic:
                    # Approximate: use centroid latitude for correction
                    centroid = geom.centroid
                    lat_rad  = math.radians(centroid.y)
                    # 1 degree lat ≈ 111320 m; 1 degree lon ≈ 111320 * cos(lat) m
                    m_per_deg_lat = 111320.0
                    m_per_deg_lon = 111320.0 * math.cos(lat_rad)
                    area_m2 = geom.area * m_per_deg_lat * m_per_deg_lon
                else:
                    # CRS is projected — shapely area is in CRS units (m²)
                    area_m2 = geom.area

                area_km2 = area_m2 / 1_000_000

                # Centroid for hover/click
                centroid = geom.centroid

                # Average NDWI over the polygon's pixels
                # (use the label-mask for cheap extraction)
                # We use a bounding-box slice for speed
                bounds    = geom.bounds  # (minx, miny, maxx, maxy)
                # Convert bounds to pixel row/col
                col_min, row_min = ~transform * (bounds[0], bounds[3])
                col_max, row_max = ~transform * (bounds[2], bounds[1])
                row_min, row_max = int(max(0, min(row_min, row_max))), int(min(ndwi.shape[0] - 1, max(row_min, row_max)))
                col_min, col_max = int(max(0, min(col_min, col_max))), int(min(ndwi.shape[1] - 1, max(col_min, col_max)))

                ndwi_slice  = ndwi[row_min:row_max + 1, col_min:col_max + 1]
                mask_slice  = final_mask[row_min:row_max + 1, col_min:col_max + 1]
                ndwi_water  = ndwi_slice[mask_slice == 1]
                avg_ndwi    = float(np.nanmean(ndwi_water)) if ndwi_water.size > 0 else float(threshold)

                feature = {
                    "type": "Feature",
                    "properties": {
                        "source":         "NDWI",
                        "ndwi_threshold": round(threshold, 4),
                        "ndwi_mean":      round(avg_ndwi, 4),
                        "area_m2":        round(area_m2, 2),
                        "area_km2":       round(area_km2, 6),
                        "centroid_lat":   round(centroid.y, 6),
                        "centroid_lon":   round(centroid.x, 6),
                    },
                    "geometry": mapping(geom_simplified),
                }

                features.append(feature)
                areas_m2.append(area_m2)

            # ----------------------------------------------------------
            # Statistics
            # ----------------------------------------------------------
            water_body_count = len(features)

            if areas_m2:
                total_area_km2   = sum(areas_m2) / 1_000_000
                largest_km2      = max(areas_m2)  / 1_000_000
                average_km2      = (sum(areas_m2) / len(areas_m2)) / 1_000_000
            else:
                total_area_km2 = largest_km2 = average_km2 = 0.0

            logger.info(
                "NDWI done — bodies=%d, total=%.4f km²",
                water_body_count, total_area_km2,
            )

            return {
                "success":          True,
                "detection_method": "NDWI",
                "ndwi_threshold":   threshold,
                "statistics": {
                    "water_body_count":       water_body_count,
                    "total_water_area_km2":   round(total_area_km2, 4),
                    "largest_water_body_km2": round(largest_km2, 4),
                    "average_water_body_km2": round(average_km2, 4),
                },
                "geojson": {
                    "type":     "FeatureCollection",
                    "features": features,
                },
            }

    except ValueError:
        raise

    except Exception as err:
        logger.exception("NDWI processing error: %s", err)
        raise RuntimeError(
            "Water detection failed. Please check the uploaded image and try again."
        )
