"""
NDWI Service (GeoTIFF Upload Pipeline)
=======================================

Handles:
  1. Raster band inspection — reads GeoTIFF metadata to identify B3/B8
  2. Delegates all water classification to water_detection.py
  3. Supports manual and adaptive (Otsu) threshold modes
  4. Returns full scientific metadata with every response

Scientific note:
  Results are described as "Sentinel-2 derived surface-water extent".
  They are NOT ground truth and must not be described as such.
"""

import io
import logging
from typing import Optional

import numpy as np
import rasterio
from rasterio.crs import CRS

from app.services.water_detection import (
    compute_ndwi,
    compute_ndwi_stats,
    compute_otsu_threshold,
    create_raw_water_mask,
    clean_water_mask,
    polygonize_water_mask,
    check_extent_plausibility,
    compute_detection_quality,
    S2_SPATIAL_RESOLUTION_M,
)

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB


# =========================================================
# BAND INSPECTION
# =========================================================

def inspect_raster_bands(file_bytes: bytes) -> dict:
    """
    Open a GeoTIFF and return band metadata.
    Attempts to auto-identify the Sentinel-2 Green (B3) and NIR (B8) bands.
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
                desc_lower = desc.strip().lower()

                if auto_green is None and (
                    "b3" in desc_lower or "green" in desc_lower
                    or color_interp.lower() == "green"
                ):
                    auto_green = i

                if auto_nir is None and (
                    "b8" in desc_lower or "nir" in desc_lower
                    or color_interp.lower() == "nir"
                ):
                    auto_nir = i

            return {
                "band_count":    band_count,
                "bands":         bands_info,
                "auto_green":    auto_green,
                "auto_nir":      auto_nir,
                "auto_detected": (auto_green is not None) and (auto_nir is not None),
                "crs":           str(src.crs) if src.crs else None,
                "transform":     list(src.transform) if src.transform else None,
            }

    except rasterio.errors.RasterioIOError as err:
        raise ValueError(f"Invalid satellite image: {err}")
    except Exception as err:
        raise ValueError(f"Could not inspect the uploaded image: {err}")


# =========================================================
# FULL NDWI DETECTION PIPELINE
# =========================================================

def process_ndwi_image(
    file_bytes: bytes,
    threshold: float,
    green_band: int,
    nir_band: int,
    min_pixels: int = 10,
    threshold_mode: str = "manual",
    debug: bool = False,
) -> dict:
    """
    Full NDWI water detection pipeline for an uploaded GeoTIFF.

    Parameters
    ----------
    file_bytes      : Raw bytes of the uploaded GeoTIFF
    threshold       : NDWI threshold when threshold_mode="manual" (default 0.30)
    green_band      : 1-based raster band index for Green (B3)
    nir_band        : 1-based raster band index for NIR (B8)
    min_pixels      : Minimum connected pixels to keep (noise filter)
    threshold_mode  : "manual" | "adaptive"
    debug           : If True, include extra diagnostics in response

    Returns
    -------
    dict with:
        success, satellite_source, spatial_resolution_m,
        selected_threshold, threshold_method, threshold_info,
        statistics (full NDWI + water + quality diagnostics),
        validation_flags, geojson, [debug_info]
    """
    logger.info(
        "NDWI processing — green=%d, nir=%d, threshold=%.3f, mode=%s",
        green_band, nir_band, threshold, threshold_mode,
    )

    try:
        with rasterio.open(io.BytesIO(file_bytes)) as src:
            # --- Band validation ---
            if green_band < 1 or green_band > src.count:
                raise ValueError(f"Green band {green_band} out of range (file has {src.count} band(s)).")
            if nir_band < 1 or nir_band > src.count:
                raise ValueError(f"NIR band {nir_band} out of range (file has {src.count} band(s)).")
            if green_band == nir_band:
                raise ValueError("Green and NIR band must be different.")

            green = src.read(green_band).astype(np.float32)
            nir   = src.read(nir_band).astype(np.float32)
            nodata     = src.nodata
            transform  = src.transform
            crs        = src.crs

            # --- Invalid pixel mask (nodata, NaN, Inf) ---
            invalid_mask = np.zeros(green.shape, dtype=bool)
            if nodata is not None:
                invalid_mask |= (green == nodata)
                invalid_mask |= (nir   == nodata)
            invalid_mask |= ~np.isfinite(green)
            invalid_mask |= ~np.isfinite(nir)

            # --- NDWI = (Green - NIR) / (Green + NIR) ---
            ndwi = compute_ndwi(green, nir, invalid_mask)

            # --- NDWI statistics ---
            ndwi_stats = compute_ndwi_stats(ndwi, invalid_mask)

            # --- Threshold selection ---
            threshold_info = {
                "selected_threshold": threshold,
                "threshold_method":   "manual",
                "otsu_threshold":     None,
                "fallback_reason":    None,
                "review_required":    False,
            }

            if threshold_mode == "adaptive":
                threshold_info = compute_otsu_threshold(
                    ndwi, invalid_mask, fallback_threshold=threshold,
                )

            effective_threshold = threshold_info["selected_threshold"]

            # --- Raw water mask ---
            raw_mask = create_raw_water_mask(ndwi, invalid_mask, effective_threshold)
            raw_water_pixels = int(raw_mask.sum())
            total_valid = ndwi_stats["valid_pixels"]
            raw_water_pct = round((raw_water_pixels / total_valid) * 100.0, 2) if total_valid > 0 else 0.0

            # Early exit — no water found
            if raw_water_pixels == 0:
                plausibility = check_extent_plausibility(0.0, threshold_info["threshold_method"], threshold_info.get("fallback_reason"))
                return _build_response(
                    threshold_info, ndwi_stats, 0.0, 0,
                    plausibility, crs, 0, 0,
                    {"type": "FeatureCollection", "features": []},
                    debug_info={"raw_water_pixels": 0, "cleaned_water_pixels": 0} if debug else None,
                )

            # --- Morphological cleanup ---
            cleaned_mask, morph_info = clean_water_mask(raw_mask, min_pixels=min_pixels)
            cleaned_water_pixels = int(cleaned_mask.sum())
            cleaned_water_pct = round((cleaned_water_pixels / total_valid) * 100.0, 2) if total_valid > 0 else 0.0

            if cleaned_water_pixels == 0:
                plausibility = check_extent_plausibility(0.0, threshold_info["threshold_method"], threshold_info.get("fallback_reason"))
                return _build_response(
                    threshold_info, ndwi_stats, 0.0, 0,
                    plausibility, crs, 0, raw_water_pixels,
                    {"type": "FeatureCollection", "features": []},
                    debug_info=morph_info if debug else None,
                )

            # --- Polygonization ---
            features = polygonize_water_mask(cleaned_mask, transform, crs, ndwi, effective_threshold)

            areas_km2 = [f["properties"]["area_km2"] for f in features]
            total_area_km2   = round(sum(areas_km2), 4)
            largest_km2      = round(max(areas_km2), 4)   if areas_km2 else 0.0
            average_km2      = round(sum(areas_km2) / len(areas_km2), 4) if areas_km2 else 0.0
            water_body_count = len(features)

            # --- Plausibility & quality ---
            plausibility = check_extent_plausibility(
                cleaned_water_pct,
                threshold_info["threshold_method"],
                threshold_info.get("fallback_reason"),
            )
            detection_quality = compute_detection_quality(
                ndwi_stats["valid_pixel_percentage"],
                cleaned_water_pct,
                plausibility["review_required"],
            )

            statistics = {
                # Water bodies
                "water_body_count":       water_body_count,
                "total_water_area_km2":   total_area_km2,
                "largest_water_body_km2": largest_km2,
                "average_water_body_km2": average_km2,
                # NDWI distribution
                "ndwi_min":    ndwi_stats["ndwi_min"],
                "ndwi_max":    ndwi_stats["ndwi_max"],
                "ndwi_mean":   ndwi_stats["ndwi_mean"],
                "ndwi_median": ndwi_stats["ndwi_median"],
                "ndwi_std":    ndwi_stats["ndwi_std"],
                # Pixel coverage
                "valid_pixels":             total_valid,
                "valid_pixel_percentage":   ndwi_stats["valid_pixel_percentage"],
                "cloud_shadow_percentage":  ndwi_stats["invalid_pixel_percentage"],
                "water_pixels":             cleaned_water_pixels,
                "water_pixel_percentage":   cleaned_water_pct,
                # Quality
                "detection_quality": detection_quality,
            }

            result = {
                "success":              True,
                "satellite_source":     "Sentinel-2 Surface Reflectance Harmonized",
                "spatial_resolution_m": S2_SPATIAL_RESOLUTION_M,
                "detection_method":     "NDWI (Green=B3, NIR=B8)",
                "selected_threshold":   effective_threshold,
                "threshold_method":     threshold_info["threshold_method"],
                "threshold_info":       threshold_info,
                "ndwi_threshold":       effective_threshold,  # backwards-compatible alias
                "statistics":           statistics,
                "validation_flags":     {
                    **plausibility,
                    "disclaimer": (
                        "This result represents Sentinel-2 derived surface-water extent. "
                        "It is NOT ground truth. Spatial resolution: 10 m. "
                        "Results may vary with cloud cover, seasonal conditions, "
                        "and NDWI threshold selection."
                    ),
                },
                "geojson": {
                    "type":     "FeatureCollection",
                    "features": features,
                },
            }

            if debug:
                result["debug_info"] = {
                    **morph_info,
                    "raw_water_pct":     raw_water_pct,
                    "cleaned_water_pct": cleaned_water_pct,
                    "otsu_threshold":    threshold_info.get("otsu_threshold"),
                }

            return result

    except ValueError:
        raise
    except Exception as err:
        logger.exception("NDWI processing error: %s", err)
        raise RuntimeError("Water detection failed. Please check the uploaded image and try again.")


# =========================================================
# RESPONSE BUILDER (EMPTY RESULT)
# =========================================================

def _build_response(
    threshold_info, ndwi_stats,
    water_pct, water_body_count,
    plausibility, crs,
    cleaned_pixels, raw_pixels,
    geojson,
    debug_info=None,
) -> dict:
    effective_threshold = threshold_info["selected_threshold"]
    detection_quality = compute_detection_quality(
        ndwi_stats["valid_pixel_percentage"],
        water_pct,
        plausibility["review_required"],
    )
    res = {
        "success":              True,
        "satellite_source":     "Sentinel-2 Surface Reflectance Harmonized",
        "spatial_resolution_m": S2_SPATIAL_RESOLUTION_M,
        "detection_method":     "NDWI (Green=B3, NIR=B8)",
        "selected_threshold":   effective_threshold,
        "threshold_method":     threshold_info["threshold_method"],
        "threshold_info":       threshold_info,
        "ndwi_threshold":       effective_threshold,
        "statistics": {
            "water_body_count":       water_body_count,
            "total_water_area_km2":   0.0,
            "largest_water_body_km2": 0.0,
            "average_water_body_km2": 0.0,
            "ndwi_min":    ndwi_stats.get("ndwi_min"),
            "ndwi_max":    ndwi_stats.get("ndwi_max"),
            "ndwi_mean":   ndwi_stats.get("ndwi_mean"),
            "ndwi_median": ndwi_stats.get("ndwi_median"),
            "ndwi_std":    ndwi_stats.get("ndwi_std"),
            "valid_pixels":             ndwi_stats.get("valid_pixels", 0),
            "valid_pixel_percentage":   ndwi_stats.get("valid_pixel_percentage", 0.0),
            "cloud_shadow_percentage":  ndwi_stats.get("invalid_pixel_percentage", 0.0),
            "water_pixels":             cleaned_pixels,
            "water_pixel_percentage":   water_pct,
            "detection_quality":        detection_quality,
        },
        "validation_flags": {
            **plausibility,
            "disclaimer": (
                "This result represents Sentinel-2 derived surface-water extent. "
                "It is NOT ground truth. Spatial resolution: 10 m."
            ),
        },
        "geojson": geojson,
    }
    if debug_info is not None:
        res["debug_info"] = debug_info
    return res
