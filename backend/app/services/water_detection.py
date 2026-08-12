"""
water_detection.py — Shared Water Classification Service
=========================================================

Single source of truth for:
  - NDWI calculation
  - Invalid pixel / cloud-shadow masking
  - Adaptive Otsu threshold computation
  - Raw and cleaned water mask generation
  - Per-component hole filling (not whole-image)
  - Connected-component size filtering
  - Polygonization with projected area calculation
  - NDWI diagnostic statistics
  - Detection quality scoring

This service is used by:
  - ndwi_service.py  (GeoTIFF upload pipeline)
  - change_detection.py  (GEE Sentinel-2 pipeline, NDWI raster path)

Scientific notation:
  All output describes "Sentinel-2 derived surface-water extent"
  at 10 m spatial resolution (when the source is Sentinel-2 10 m data).
  Results are NOT ground truth and must NOT be described as such.
"""

import logging
import math
from typing import Optional

import numpy as np
from scipy.ndimage import (
    binary_opening,
    binary_fill_holes,
    label as scipy_label,
)
from shapely.geometry import shape, mapping
from shapely.validation import make_valid

try:
    from rasterio.features import shapes as rasterio_shapes
    from rasterio.crs import CRS
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False


logger = logging.getLogger(__name__)


# =========================================================
# CONSTANTS
# =========================================================

# Sentinel-2 native spatial resolution (metres)
S2_SPATIAL_RESOLUTION_M = 10

# Conservatively small simplification tolerance in degrees (≈ 1 m at equator)
# Do not increase — over-simplification removes real shoreline detail
SIMPLIFY_TOLERANCE_DEG = 0.00005

# Otsu plausibility bounds: if the adaptive threshold falls outside this range
# it is likely not physically meaningful for open-surface water detection
OTSU_MIN_PLAUSIBLE = 0.05
OTSU_MAX_PLAUSIBLE = 0.55

# Minimum fraction of pixels above threshold to flag "implausibly large extent"
IMPLAUSIBLE_WATER_FRACTION_HIGH = 0.70   # > 70 % of valid pixels flagged as water → review
IMPLAUSIBLE_WATER_FRACTION_LOW  = 0.0    # 0 % water with reasonable threshold → low quality


# =========================================================
# NDWI CALCULATION
# =========================================================

def compute_ndwi(
    green: np.ndarray,
    nir: np.ndarray,
    invalid_mask: np.ndarray,
) -> np.ndarray:
    """
    NDWI = (Green - NIR) / (Green + NIR)

    Safe division: pixels where |Green + NIR| < 1e-6 are set to NaN.
    Invalid (cloud/shadow/nodata) pixels are set to NaN.

    Returns float32 array with NaN for invalid pixels.
    """
    denominator = green + nir
    safe_denom = np.where(np.abs(denominator) < 1e-6, np.nan, denominator)
    ndwi = np.where(invalid_mask, np.nan, (green - nir) / safe_denom)
    return ndwi.astype(np.float32)


# =========================================================
# NDWI STATISTICS
# =========================================================

def compute_ndwi_stats(
    ndwi: np.ndarray,
    invalid_mask: np.ndarray,
) -> dict:
    """
    Compute diagnostic statistics over valid (non-NaN, non-invalid) pixels.

    Returns dict with: ndwi_min, ndwi_max, ndwi_mean, ndwi_median,
                       ndwi_std, valid_pixels, total_pixels,
                       valid_pixel_percentage, invalid_pixel_percentage
    """
    total_pixels = int(ndwi.size)
    valid_mask = np.isfinite(ndwi) & ~invalid_mask
    valid_ndwi = ndwi[valid_mask]

    if valid_ndwi.size == 0:
        return {
            "ndwi_min": None,
            "ndwi_max": None,
            "ndwi_mean": None,
            "ndwi_median": None,
            "ndwi_std": None,
            "valid_pixels": 0,
            "total_pixels": total_pixels,
            "valid_pixel_percentage": 0.0,
            "invalid_pixel_percentage": 100.0,
        }

    valid_count = int(valid_ndwi.size)
    invalid_count = int(invalid_mask.sum())

    return {
        "ndwi_min":    round(float(np.min(valid_ndwi)), 4),
        "ndwi_max":    round(float(np.max(valid_ndwi)), 4),
        "ndwi_mean":   round(float(np.mean(valid_ndwi)), 4),
        "ndwi_median": round(float(np.median(valid_ndwi)), 4),
        "ndwi_std":    round(float(np.std(valid_ndwi)), 4),
        "valid_pixels":            valid_count,
        "total_pixels":            total_pixels,
        "valid_pixel_percentage":  round((valid_count / total_pixels) * 100.0, 2),
        "invalid_pixel_percentage": round((invalid_count / total_pixels) * 100.0, 2),
    }


# =========================================================
# ADAPTIVE THRESHOLD (OTSU ON NDWI HISTOGRAM)
# =========================================================

def compute_otsu_threshold(
    ndwi: np.ndarray,
    invalid_mask: np.ndarray,
    n_bins: int = 256,
    fallback_threshold: float = 0.30,
) -> dict:
    """
    Compute an adaptive NDWI threshold using Otsu's method.

    Otsu finds the threshold that minimises intra-class variance between
    the "water" and "non-water" distributions.

    Returns:
        selected_threshold : float
        threshold_method   : "adaptive_otsu" | "manual_fallback"
        otsu_threshold     : float  (always returned for transparency)
        fallback_reason    : str    (None if Otsu was accepted)
        review_required    : bool
    """
    valid_ndwi = ndwi[np.isfinite(ndwi) & ~invalid_mask]

    if valid_ndwi.size < 100:
        return {
            "selected_threshold": fallback_threshold,
            "threshold_method":   "manual_fallback",
            "otsu_threshold":     None,
            "fallback_reason":    "Insufficient valid pixels for Otsu analysis.",
            "review_required":    True,
        }

    # Build histogram over NDWI range [-1, 1]
    counts, bin_edges = np.histogram(valid_ndwi, bins=n_bins, range=(-1.0, 1.0))
    bin_centres = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    total = counts.sum()

    if total == 0:
        return {
            "selected_threshold": fallback_threshold,
            "threshold_method":   "manual_fallback",
            "otsu_threshold":     None,
            "fallback_reason":    "No valid pixels in NDWI histogram.",
            "review_required":    True,
        }

    # Otsu's criterion
    probs = counts / total
    best_var = -1.0
    best_t   = 0.0

    weight_bg = 0.0
    mean_bg   = 0.0

    total_mean = float(np.sum(probs * bin_centres))

    for k in range(1, n_bins):
        weight_bg += probs[k - 1]
        weight_fg  = 1.0 - weight_bg

        if weight_bg < 1e-6 or weight_fg < 1e-6:
            continue

        mean_bg += probs[k - 1] * bin_centres[k - 1]
        mean_fg = (total_mean - mean_bg) / weight_fg

        between_var = weight_bg * weight_fg * (mean_bg / weight_bg - mean_fg) ** 2
        if between_var > best_var:
            best_var = between_var
            best_t   = bin_centres[k - 1]

    otsu_t = round(float(best_t), 4)

    # Plausibility check
    fallback_reason = None
    if otsu_t < OTSU_MIN_PLAUSIBLE:
        fallback_reason = (
            f"Otsu threshold {otsu_t:.4f} is below minimum plausible value "
            f"{OTSU_MIN_PLAUSIBLE} for open-surface water detection. "
            f"Scene may have extensive wet soil, shadows, or low-NDWI water."
        )
    elif otsu_t > OTSU_MAX_PLAUSIBLE:
        fallback_reason = (
            f"Otsu threshold {otsu_t:.4f} exceeds maximum plausible value "
            f"{OTSU_MAX_PLAUSIBLE}. Scene may lack sufficient water or "
            f"contain spectral confusion."
        )

    if fallback_reason:
        return {
            "selected_threshold": fallback_threshold,
            "threshold_method":   "manual_fallback",
            "otsu_threshold":     otsu_t,
            "fallback_reason":    fallback_reason,
            "review_required":    True,
        }

    return {
        "selected_threshold": otsu_t,
        "threshold_method":   "adaptive_otsu",
        "otsu_threshold":     otsu_t,
        "fallback_reason":    None,
        "review_required":    False,
    }


# =========================================================
# WATER MASK GENERATION
# =========================================================

def create_raw_water_mask(
    ndwi: np.ndarray,
    invalid_mask: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """
    Raw binary water mask: NDWI >= threshold AND valid (non-cloud, non-nodata) pixel.

    Cloud/shadow/nodata pixels are NEVER classified as water.
    They remain as background (0) — this means they cannot be counted as
    water loss or water gain in temporal comparison.

    Returns uint8 array (1=water, 0=non-water/invalid).
    """
    raw = (
        np.isfinite(ndwi) &
        ~invalid_mask &
        (ndwi >= threshold)
    ).astype(np.uint8)
    return raw


# =========================================================
# MORPHOLOGICAL CLEANUP
# =========================================================

def clean_water_mask(
    raw_mask: np.ndarray,
    min_pixels: int = 10,
) -> tuple:
    """
    3-stage conservative morphological cleanup:

    Stage 1 — Binary Opening (3×3):
        Removes isolated 1-2 pixel noise specks.
        Does NOT destroy narrow channels (3×3 is conservative).

    Stage 2 — Per-Component Hole Filling:
        For each connected water component, fill enclosed interior holes.
        This handles turbid/vegetated patches inside a closed lake.

        IMPORTANT: This is done PER COMPONENT, not on the whole image.
        Whole-image fill would incorrectly fill open embayments
        (river mouths, coastal inlets) that connect to non-water areas.

    Stage 3 — Connected Component Size Filter:
        Remove components below min_pixels threshold.
        For Sentinel-2 10 m: min_pixels=10 ≈ 1000 m² (0.001 km²).
        This removes sub-pixel noise while preserving genuine small ponds.

    Returns:
        cleaned_mask : uint8 ndarray
        debug_info   : dict with component counts and pixel counts
    """
    # Stage 1: Remove isolated specks
    opened = binary_opening(raw_mask.astype(bool), structure=np.ones((3, 3)))

    # Stage 2: Label components, then fill holes per component
    labelled, n_components = scipy_label(opened)

    # Per-component hole filling
    filled = np.zeros_like(opened, dtype=bool)
    for comp_id in range(1, n_components + 1):
        component = (labelled == comp_id)
        # Fill holes only within this component's bounding box for efficiency
        rows = np.any(component, axis=1)
        cols = np.any(component, axis=0)
        if not rows.any():
            continue
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        # Expand bounding box slightly to allow hole fill at edge
        rmin = max(0, rmin - 1)
        rmax = min(component.shape[0] - 1, rmax + 1)
        cmin = max(0, cmin - 1)
        cmax = min(component.shape[1] - 1, cmax + 1)

        patch = component[rmin:rmax + 1, cmin:cmax + 1]
        filled_patch = binary_fill_holes(patch)
        filled[rmin:rmax + 1, cmin:cmax + 1] |= filled_patch

    # Stage 3: Re-label and apply min-size filter
    labelled2, n_components2 = scipy_label(filled)
    component_sizes = np.bincount(labelled2.ravel())
    keep_labels = set(
        idx for idx, cnt in enumerate(component_sizes)
        if idx > 0 and cnt >= min_pixels
    )

    cleaned = np.isin(labelled2, list(keep_labels)).astype(np.uint8)

    return cleaned, {
        "components_after_opening":     n_components,
        "components_after_size_filter": int(len(keep_labels)),
        "raw_water_pixels":             int(raw_mask.sum()),
        "opened_water_pixels":          int(opened.sum()),
        "filled_water_pixels":          int(filled.sum()),
        "cleaned_water_pixels":         int(cleaned.sum()),
    }


# =========================================================
# AREA CALCULATION (PROJECTED, NOT DEGREE SQUARED)
# =========================================================

def _area_m2_projected(geom, crs) -> float:
    """
    Calculate polygon area in m² using projected coordinates.

    If pyproj is available, reproject to UTM then use planar geometry.
    Otherwise fall back to Haversine-based approximation (less accurate
    but avoids the degree² error).
    """
    centroid = geom.centroid

    if HAS_PYPROJ:
        # Determine UTM zone from centroid
        utm_zone = int((centroid.x + 180) / 6) + 1
        south = centroid.y < 0
        utm_epsg = 32700 + utm_zone if south else 32600 + utm_zone
        try:
            transformer = Transformer.from_crs(
                crs.to_epsg() if hasattr(crs, "to_epsg") else 4326,
                utm_epsg,
                always_xy=True,
            )
            from shapely.ops import transform as shapely_transform
            projected = shapely_transform(transformer.transform, geom)
            return float(projected.area)
        except Exception as e:
            logger.debug("UTM projection failed (%s), using haversine fallback", e)

    # Haversine-based fallback for geographic CRS
    lat_rad = math.radians(centroid.y)
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(lat_rad)
    return float(geom.area) * m_per_deg_lat * m_per_deg_lon


# =========================================================
# POLYGONIZATION
# =========================================================

def polygonize_water_mask(
    final_mask: np.ndarray,
    transform,
    crs,
    ndwi: np.ndarray,
    threshold: float,
) -> list:
    """
    Convert cleaned binary water mask to GeoJSON features.

    Each feature includes:
        area_m2, area_km2, centroid_lat, centroid_lon,
        ndwi_mean (mean NDWI of water pixels inside polygon),
        ndwi_threshold, source, spatial_resolution_m

    Geometry is:
        1. make_valid()  — fix any self-intersections
        2. simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True) — remove pixel staircase
        The tolerance is ~5m at equator — tight enough to follow the actual
        water boundary while removing sub-pixel rasterization artifacts.
    """
    if not HAS_RASTERIO:
        raise RuntimeError("rasterio is required for polygonization.")

    features = []

    for geom_dict, value in rasterio_shapes(final_mask, mask=final_mask, transform=transform):
        if value == 0:
            continue

        geom = shape(geom_dict)
        geom = make_valid(geom)
        if geom.is_empty or not geom.is_valid:
            continue

        # Conservative simplification — removes pixel staircase only
        geom_simp = geom.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        if geom_simp.is_empty:
            geom_simp = geom

        # Area in m² using projected CRS
        area_m2 = _area_m2_projected(geom, crs)
        area_km2 = area_m2 / 1_000_000.0

        centroid = geom_simp.centroid

        # Mean NDWI within the polygon's bounding box pixels (water-classified only)
        bounds = geom.bounds
        try:
            col_min, row_max = ~transform * (bounds[0], bounds[1])
            col_max, row_min = ~transform * (bounds[2], bounds[3])
            row_min = int(max(0, min(row_min, row_max)))
            row_max = int(min(ndwi.shape[0] - 1, max(row_min, row_max)))
            col_min = int(max(0, min(col_min, col_max)))
            col_max = int(min(ndwi.shape[1] - 1, max(col_min, col_max)))
            ndwi_patch = ndwi[row_min:row_max + 1, col_min:col_max + 1]
            mask_patch = final_mask[row_min:row_max + 1, col_min:col_max + 1]
            ndwi_water = ndwi_patch[mask_patch == 1]
            avg_ndwi = float(np.nanmean(ndwi_water)) if ndwi_water.size > 0 else float(threshold)
        except Exception:
            avg_ndwi = float(threshold)

        feature = {
            "type": "Feature",
            "properties": {
                "source":                "Sentinel-2 derived surface-water extent",
                "spatial_resolution_m":  S2_SPATIAL_RESOLUTION_M,
                "ndwi_threshold":        round(threshold, 4),
                "ndwi_mean":             round(avg_ndwi, 4),
                "area_m2":               round(area_m2, 1),
                "area_km2":              round(area_km2, 6),
                "centroid_lat":          round(centroid.y, 6),
                "centroid_lon":          round(centroid.x, 6),
            },
            "geometry": mapping(geom_simp),
        }
        features.append(feature)

    return features


# =========================================================
# IMPLAUSIBILITY CHECK
# =========================================================

def check_extent_plausibility(
    water_pixel_percentage: float,
    threshold_method: str,
    fallback_reason: Optional[str],
) -> dict:
    """
    Flag detections that may require scientific review.

    Returns:
        review_required : bool
        review_reasons  : list of str
    """
    reasons = []

    if fallback_reason:
        reasons.append(f"Adaptive threshold fallback: {fallback_reason}")

    if water_pixel_percentage > IMPLAUSIBLE_WATER_FRACTION_HIGH * 100:
        reasons.append(
            f"Water classification covers {water_pixel_percentage:.1f}% of valid pixels "
            f"(> {IMPLAUSIBLE_WATER_FRACTION_HIGH * 100:.0f}%). "
            f"Scene may include clouds, shadows, or spectral confusion at this threshold."
        )

    if water_pixel_percentage == 0.0:
        reasons.append(
            "No water pixels detected. The threshold may be too high, "
            "the AOI may not contain open water, or cloud masking may be too aggressive."
        )

    return {
        "review_required": len(reasons) > 0,
        "review_reasons":  reasons,
    }


# =========================================================
# DETECTION QUALITY SCORE
# =========================================================

def compute_detection_quality(
    valid_pixel_percentage: float,
    water_pixel_percentage: float,
    review_required: bool,
) -> str:
    """
    Returns HIGH / MEDIUM / LOW based on measurable scene properties.

    NOT a validated accuracy metric.
    Based on:
        - valid (cloud-free) pixel coverage
        - whether the result requires scientific review
    """
    if review_required:
        return "LOW"
    if valid_pixel_percentage >= 90.0:
        return "HIGH"
    if valid_pixel_percentage >= 70.0:
        return "MEDIUM"
    return "LOW"
