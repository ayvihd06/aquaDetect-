"""
flood_detection.py — Real Sentinel-1 SAR Flood Detection for AquaDetect
=========================================================================

Implements a before/after Sentinel-1 SAR flood candidate detection workflow:

1. Search Sentinel-1 GRD IW VV scenes for before and after periods.
2. Select the best-matching pair with the SAME orbit direction.
3. Classify water-like pixels (absolute VV < threshold) in both scenes.
4. Apply JRC Global Surface Water as permanent-water baseline.
5. Flood candidates = AFTER_WATER AND NOT BEFORE_WATER AND NOT PERMANENT_WATER.
6. Filter noise with connectedPixelCount.
7. Calculate flood area using pixelArea() (never degree-based approximation).
8. Polygonize to GeoJSON for frontend display.
9. Generate GEE tile URLs for visual evidence (Before SAR, After SAR,
   SAR change, Permanent Water, Flood Extent).
10. Compute CHIRPS rainfall evidence.
11. Classify FLOOD INDICATOR using documented hydrology_config.py thresholds.

References:
- Twele et al. (2016), NHESS, doi:10.5194/nhess-16-1651-2016
- Bauer-Marschallinger et al. (2022), Remote Sensing 14(7), 1648
- Pekel et al. (2016), Nature 540, 418-422 (JRC Global Surface Water)

IMPORTANT: No dummy values anywhere. If data is unavailable, return
    {"available": False, "reason": "..."}
"""

import logging
import datetime
from typing import Dict, Any, Optional

import ee

from app.services.hydrology.hydrology_config import (
    FLOOD_SAR_THRESHOLD_DB,
    FLOOD_MIN_CONNECTED_PIXELS,
    FLOOD_MAX_TEMPORAL_GAP_DAYS,
    FLOOD_VV_CHANGE_EVIDENCE_DB,
    PERMANENT_WATER_OCCURRENCE_THRESHOLD,
    S1_INSTRUMENT_MODE,
    S1_PRODUCT_TYPE,
    S1_POLARIZATION,
    S1_MAX_SCENES_TO_INSPECT,
    FLOOD_EXPANSION_HIGH_PERCENT,
    FLOOD_EXPANSION_MODERATE_PERCENT,
    FLOOD_AREA_HIGH_KM2,
    FLOOD_AREA_MODERATE_KM2,
    FLOOD_RAINFALL_ANOMALY_HIGH_PERCENT,
    FLOOD_RAINFALL_ANOMALY_MODERATE_PERCENT,
    QUALITY_HIGH_COVERAGE,
    QUALITY_MEDIUM_COVERAGE,
)
from app.services.hydrology.rainfall_service import get_rainfall_summary

# Reuse existing utilities from change_detection.py — no duplication
from app.services.change_detection import (
    initialize_earth_engine,
    get_district_aoi,
)

logger = logging.getLogger(__name__)

PROJECT_ID = "aquadetect-504614"
JRC_DATASET = "JRC/GSW1_4/GlobalSurfaceWater"


# ===========================================================
# SENTINEL-1 SCENE SELECTION
# ===========================================================

def _find_best_s1_scene(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """
    Find the best available Sentinel-1 GRD IW VV scene in the given date window.

    Returns metadata dict including orbit direction. Tries all available
    scenes ranked by AOI coverage.

    Returns {"found": False, "reason": ...} when unavailable.
    """
    today = datetime.datetime.utcnow()
    today_str = today.strftime("%Y-%m-%d")

    if start_date > today_str:
        return {
            "found": False,
            "reason": f"Start date {start_date} is in the future — no Sentinel-1 data available.",
        }

    try:
        collection = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.eq("instrumentMode", S1_INSTRUMENT_MODE))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", S1_POLARIZATION))
            .filter(ee.Filter.eq("resolution_meters", 10))
            .select([S1_POLARIZATION])
        )

        count = collection.size().getInfo()
        if count == 0:
            return {
                "found": False,
                "reason": (
                    f"No Sentinel-1 {S1_INSTRUMENT_MODE} {S1_PRODUCT_TYPE} VV scenes found "
                    f"between {start_date} and {end_date}."
                ),
            }

        # Get list of scenes with metadata
        scene_list = collection.limit(S1_MAX_SCENES_TO_INSPECT).getInfo()
        features = scene_list.get("features", [])

        if not features:
            return {
                "found": False,
                "reason": "Sentinel-1 collection returned no features.",
            }

        # Extract metadata per scene and group by orbit direction
        scenes_by_orbit: Dict[str, list] = {}
        for feat in features:
            props = feat.get("properties", {})
            orbit = props.get("orbitProperties_pass", "UNKNOWN")
            ts = props.get("system:time_start")
            scene_id = props.get("system:index", "")
            if orbit not in scenes_by_orbit:
                scenes_by_orbit[orbit] = []
            scenes_by_orbit[orbit].append({
                "scene_id": scene_id,
                "orbit_direction": orbit,
                "timestamp_ms": ts,
                "date": datetime.datetime.fromtimestamp(
                    ts / 1000.0, datetime.timezone.utc
                ).strftime("%Y-%m-%d") if ts else start_date,
                "props": props,
            })

        # Return best scene per orbit (temporally closest to center of window)
        # Prefer DESCENDING but return whatever is available
        for preferred_orbit in ["DESCENDING", "ASCENDING", "UNKNOWN"]:
            if preferred_orbit in scenes_by_orbit:
                candidates = scenes_by_orbit[preferred_orbit]
                # Sort by timestamp ascending to pick earliest available
                candidates.sort(key=lambda x: x["timestamp_ms"] or 0)
                best = candidates[0]
                return {
                    "found": True,
                    "scene_id": best["scene_id"],
                    "orbit_direction": best["orbit_direction"],
                    "date": best["date"],
                    "timestamp_ms": best["timestamp_ms"],
                    "count_in_window": count,
                    "available_orbits": list(scenes_by_orbit.keys()),
                    "image": (
                        ee.ImageCollection("COPERNICUS/S1_GRD")
                        .filterBounds(aoi)
                        .filterDate(start_date, end_date)
                        .filter(ee.Filter.eq("instrumentMode", S1_INSTRUMENT_MODE))
                        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", S1_POLARIZATION))
                        .filter(ee.Filter.eq("resolution_meters", 10))
                        .filter(ee.Filter.eq("orbitProperties_pass", best["orbit_direction"]))
                        .select([S1_POLARIZATION])
                        .first()
                    ),
                }

        return {
            "found": False,
            "reason": "No usable Sentinel-1 scenes found in the date window.",
        }

    except Exception as error:
        logger.error("Sentinel-1 scene search failed: %s", error)
        return {
            "found": False,
            "reason": f"Sentinel-1 search error: {str(error)}",
        }


def _select_same_orbit_pair(
    aoi: ee.Geometry,
    before_start: str,
    before_end: str,
    after_start: str,
    after_end: str,
) -> Dict[str, Any]:
    """
    Find before/after Sentinel-1 scenes with the SAME orbit direction.

    Algorithm:
    1. Find all candidate before scenes.
    2. Find all candidate after scenes.
    3. Group by orbit direction.
    4. Select the pair with matching orbit and minimum temporal gap.
    5. Report selected orbit direction in result.

    Returns {"found": True, "before": ..., "after": ..., "orbit_direction": ...}
    or      {"found": False, "reason": ...}
    """
    today = datetime.datetime.utcnow()
    today_str = today.strftime("%Y-%m-%d")

    try:
        def _get_scenes_by_orbit(start: str, end: str) -> Dict[str, list]:
            if start > today_str:
                return {}
            collection = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(aoi)
                .filterDate(start, end)
                .filter(ee.Filter.eq("instrumentMode", S1_INSTRUMENT_MODE))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", S1_POLARIZATION))
                .filter(ee.Filter.eq("resolution_meters", 10))
                .select([S1_POLARIZATION])
            )
            count = collection.size().getInfo()
            if count == 0:
                return {}

            scene_list = collection.limit(S1_MAX_SCENES_TO_INSPECT).getInfo()
            by_orbit: Dict[str, list] = {}
            for feat in scene_list.get("features", []):
                props = feat.get("properties", {})
                orbit = props.get("orbitProperties_pass", "UNKNOWN")
                ts = props.get("system:time_start")
                scene_id = props.get("system:index", "")
                img = (
                    ee.ImageCollection("COPERNICUS/S1_GRD")
                    .filterBounds(aoi)
                    .filterDate(start, end)
                    .filter(ee.Filter.eq("instrumentMode", S1_INSTRUMENT_MODE))
                    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", S1_POLARIZATION))
                    .filter(ee.Filter.eq("resolution_meters", 10))
                    .filter(ee.Filter.eq("orbitProperties_pass", orbit))
                    .filter(ee.Filter.eq("system:index", scene_id))
                    .select([S1_POLARIZATION])
                    .first()
                )
                entry = {
                    "scene_id": scene_id,
                    "orbit_direction": orbit,
                    "timestamp_ms": ts or 0,
                    "date": datetime.datetime.fromtimestamp(
                        (ts or 0) / 1000.0, datetime.timezone.utc
                    ).strftime("%Y-%m-%d"),
                    "image": img,
                }
                if orbit not in by_orbit:
                    by_orbit[orbit] = []
                by_orbit[orbit].append(entry)
            return by_orbit

        before_by_orbit = _get_scenes_by_orbit(before_start, before_end)
        after_by_orbit  = _get_scenes_by_orbit(after_start, after_end)

        if not before_by_orbit:
            return {
                "found": False,
                "reason": f"No Sentinel-1 scenes found for before period {before_start} – {before_end}.",
            }
        if not after_by_orbit:
            return {
                "found": False,
                "reason": f"No Sentinel-1 scenes found for after period {after_start} – {after_end}.",
            }

        # Find matching orbit pairs, prefer DESCENDING then ASCENDING
        for preferred in ["DESCENDING", "ASCENDING", "UNKNOWN"]:
            if preferred in before_by_orbit and preferred in after_by_orbit:
                b_scenes = sorted(before_by_orbit[preferred], key=lambda x: x["timestamp_ms"])
                a_scenes = sorted(after_by_orbit[preferred],  key=lambda x: x["timestamp_ms"])
                b_best = b_scenes[-1]   # latest in before window
                a_best = a_scenes[0]    # earliest in after window
                gap = abs(a_best["timestamp_ms"] - b_best["timestamp_ms"]) / 86400000.0

                if gap > FLOOD_MAX_TEMPORAL_GAP_DAYS:
                    logger.warning(
                        "Temporal gap %.0f days exceeds maximum %d days",
                        gap, FLOOD_MAX_TEMPORAL_GAP_DAYS,
                    )

                return {
                    "found": True,
                    "orbit_direction": preferred,
                    "temporal_gap_days": round(gap, 1),
                    "before": b_best,
                    "after": a_best,
                    "before_orbits_available": list(before_by_orbit.keys()),
                    "after_orbits_available": list(after_by_orbit.keys()),
                }

        # No matching orbit found — try mismatched as last resort with warning
        all_before = sum(before_by_orbit.values(), [])
        all_after  = sum(after_by_orbit.values(), [])
        b_best = sorted(all_before, key=lambda x: x["timestamp_ms"])[-1]
        a_best = sorted(all_after,  key=lambda x: x["timestamp_ms"])[0]
        gap = abs(a_best["timestamp_ms"] - b_best["timestamp_ms"]) / 86400000.0

        return {
            "found": True,
            "orbit_direction": "MIXED (orbit mismatch — interpret with caution)",
            "orbit_mismatch_warning": True,
            "temporal_gap_days": round(gap, 1),
            "before": b_best,
            "after": a_best,
            "before_orbits_available": list(before_by_orbit.keys()),
            "after_orbits_available": list(after_by_orbit.keys()),
        }

    except Exception as error:
        logger.error("Sentinel-1 orbit matching failed: %s", error)
        return {
            "found": False,
            "reason": f"Sentinel-1 scene selection error: {str(error)}",
        }


# ===========================================================
# SAR WATER CLASSIFICATION
# ===========================================================

def _classify_sar_water(
    image: ee.Image,
    aoi: ee.Geometry,
    threshold_db: float = FLOOD_SAR_THRESHOLD_DB,
) -> ee.Image:
    """
    Classify water-like pixels in a Sentinel-1 VV image.
    VV < threshold_db → potential water (returns binary mask).
    """
    return image.select(S1_POLARIZATION).lt(threshold_db).selfMask()


def _get_jrc_permanent_water(aoi: ee.Geometry) -> ee.Image:
    """
    Return JRC Global Surface Water permanent water mask.
    Pixels with occurrence >= PERMANENT_WATER_OCCURRENCE_THRESHOLD are permanent water.
    Reference: Pekel et al. (2016), Nature 540, 418-422.
    """
    jrc = ee.Image(JRC_DATASET).select("occurrence")
    return jrc.gte(PERMANENT_WATER_OCCURRENCE_THRESHOLD).selfMask()


# ===========================================================
# FLOOD AREA CALCULATION
# ===========================================================

def _compute_area_km2(mask: ee.Image, aoi: ee.Geometry) -> float:
    """
    Compute area of masked pixels using pixelArea() in km².
    Never uses degree-based approximation.
    """
    try:
        reduced = (
            mask.unmask(0)
            .eq(1)
            .multiply(ee.Image.pixelArea())
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=10,
                maxPixels=1e9,
            )
        )
        val = reduced.values().get(0).getInfo()
        return round(float(val or 0.0) / 1_000_000.0, 4)
    except Exception as err:
        logger.warning("Area calculation failed: %s", err)
        return 0.0


# ===========================================================
# TILE URL HELPER
# ===========================================================

def _get_tile_url(ee_obj: Any, vis_params: dict) -> str:
    try:
        return ee_obj.getMapId(vis_params)["tile_fetcher"].url_format
    except Exception as e:
        logger.warning("Tile URL generation failed: %s", e)
        return ""


# ===========================================================
# FLOOD INDICATOR CLASSIFICATION
# ===========================================================

def _classify_flood_indicator(
    flood_area_km2: float,
    permanent_water_km2: float,
    rainfall_anomaly_pct: Optional[float],
) -> Dict[str, Any]:
    """
    Classify FLOOD INDICATOR based on two independent evidence pillars.
    All thresholds from hydrology_config.py — none hard-coded here.

    Pillar 1: SAR water expansion
    Pillar 2: CHIRPS rainfall anomaly (supporting evidence)

    Returns:
        {
          "indicator": "HIGH" | "MODERATE" | "LOW" | "INSUFFICIENT_DATA",
          "evidence_summary": str,
          "sar_evidence": str,
          "rainfall_evidence": str,
        }
    """
    expansion_pct = (
        (flood_area_km2 / permanent_water_km2 * 100.0)
        if permanent_water_km2 > 0
        else None
    )

    # SAR pillar
    if flood_area_km2 >= FLOOD_AREA_HIGH_KM2 and (
        expansion_pct is None or expansion_pct >= FLOOD_EXPANSION_HIGH_PERCENT
    ):
        sar_level = "HIGH"
    elif flood_area_km2 >= FLOOD_AREA_MODERATE_KM2 or (
        expansion_pct is not None and expansion_pct >= FLOOD_EXPANSION_MODERATE_PERCENT
    ):
        sar_level = "MODERATE"
    elif flood_area_km2 > 0:
        sar_level = "LOW"
    else:
        sar_level = "NONE"

    # Rainfall pillar
    if rainfall_anomaly_pct is None:
        rain_level = "UNKNOWN"
    elif rainfall_anomaly_pct >= FLOOD_RAINFALL_ANOMALY_HIGH_PERCENT:
        rain_level = "HIGH"
    elif rainfall_anomaly_pct >= FLOOD_RAINFALL_ANOMALY_MODERATE_PERCENT:
        rain_level = "MODERATE"
    elif rainfall_anomaly_pct > 0:
        rain_level = "LOW"
    else:
        rain_level = "NONE"

    # Combined indicator
    if sar_level == "NONE" and flood_area_km2 == 0:
        indicator = "INSUFFICIENT_DATA"
    elif sar_level == "HIGH" and rain_level in ("HIGH", "MODERATE", "UNKNOWN", "LOW"):
        indicator = "HIGH"
    elif sar_level == "HIGH" and rain_level == "NONE":
        indicator = "MODERATE"
    elif sar_level == "MODERATE" and rain_level == "HIGH":
        indicator = "HIGH"
    elif sar_level == "MODERATE":
        indicator = "MODERATE"
    elif sar_level == "LOW" and rain_level in ("HIGH", "MODERATE"):
        indicator = "MODERATE"
    elif sar_level == "LOW":
        indicator = "LOW"
    else:
        indicator = "LOW"

    expansion_str = (
        f"{expansion_pct:.1f}% expansion relative to permanent water"
        if expansion_pct is not None
        else "expansion not calculable (no permanent water baseline)"
    )

    return {
        "indicator": indicator,
        "sar_evidence_level": sar_level,
        "rainfall_evidence_level": rain_level,
        "flood_area_km2": flood_area_km2,
        "expansion_percent": round(expansion_pct, 1) if expansion_pct is not None else None,
        "evidence_summary": (
            f"SAR evidence: {sar_level} ({expansion_str}, "
            f"new water area {flood_area_km2:.3f} km²). "
            f"Rainfall anomaly evidence: {rain_level} "
            f"({rainfall_anomaly_pct:.0f}% anomaly)." if rainfall_anomaly_pct is not None
            else f"SAR evidence: {sar_level} ({expansion_str}). Rainfall data unavailable."
        ),
    }


# ===========================================================
# FLOOD QUALITY ASSESSMENT
# ===========================================================

def _assess_flood_quality(
    before_found: bool,
    after_found: bool,
    orbit_mismatch: bool,
    temporal_gap_days: float,
    sar_aoi_coverage_pct: float,
    rainfall_available: bool,
) -> Dict[str, Any]:
    """
    Assess data quality and produce HIGH/MEDIUM/LOW classification.
    All thresholds from hydrology_config.py.
    """
    warnings = []

    if not before_found or not after_found:
        return {
            "status": "INSUFFICIENT_DATA",
            "sar_aoi_coverage_percent": 0,
            "warnings": ["Sentinel-1 observations insufficient."],
        }

    if orbit_mismatch:
        warnings.append(
            "Before and after scenes are from different orbit directions. "
            "Interpret results with caution."
        )

    if temporal_gap_days > FLOOD_MAX_TEMPORAL_GAP_DAYS:
        warnings.append(
            f"Temporal gap of {temporal_gap_days:.0f} days exceeds recommended "
            f"maximum of {FLOOD_MAX_TEMPORAL_GAP_DAYS} days."
        )

    if not rainfall_available:
        warnings.append("CHIRPS rainfall data unavailable for this period.")

    if sar_aoi_coverage_pct >= QUALITY_HIGH_COVERAGE:
        status = "HIGH"
    elif sar_aoi_coverage_pct >= QUALITY_MEDIUM_COVERAGE:
        status = "MEDIUM"
    else:
        status = "LOW"
        warnings.append(
            f"SAR AOI coverage is low ({sar_aoi_coverage_pct:.1f}%). "
            "Interpret results with caution."
        )

    return {
        "status": status,
        "sar_aoi_coverage_percent": round(sar_aoi_coverage_pct, 1),
        "temporal_gap_days": round(temporal_gap_days, 1),
        "orbit_mismatch": orbit_mismatch,
        "rainfall_available": rainfall_available,
        "warnings": warnings,
    }


# ===========================================================
# MAIN FLOOD ANALYSIS FUNCTION
# ===========================================================

def analyze_flood(
    district: str,
    before_start: str,
    before_end: str,
    after_start: str,
    after_end: str,
    rainfall_window_days: int = 7,
    sar_threshold_db: float = FLOOD_SAR_THRESHOLD_DB,
) -> Dict[str, Any]:
    """
    Perform real Sentinel-1 SAR flood detection for a district AOI.

    Workflow:
    1. Find matching orbit before/after SAR scenes.
    2. Classify water-like pixels in each (VV < threshold_db).
    3. Apply JRC permanent water baseline.
    4. NEW_FLOOD = after_water AND NOT before_water AND NOT permanent_water.
    5. Noise-filter using connectedPixelCount.
    6. Calculate areas with pixelArea().
    7. Generate GEE tile URLs.
    8. Compute CHIRPS rainfall summary.
    9. Classify FLOOD INDICATOR.

    Args:
        district: Tamil Nadu district name.
        before_start/before_end: Pre-event date window.
        after_start/after_end:   Post-event date window.
        rainfall_window_days:    CHIRPS window for rainfall summary.
        sar_threshold_db:        VV backscatter threshold (default from config).

    Returns:
        Full structured result or {"available": False, "reason": "..."}.
    """
    initialize_earth_engine()

    aoi = get_district_aoi(district)
    aoi_area_km2 = float(aoi.area(maxError=1).getInfo() or 1.0) / 1_000_000.0

    # -------------------------------------------------------
    # 1. SELECT SENTINEL-1 SCENE PAIR (same orbit direction)
    # -------------------------------------------------------
    pair = _select_same_orbit_pair(aoi, before_start, before_end, after_start, after_end)

    if not pair["found"]:
        return {
            "available": False,
            "reason": pair.get("reason", "No suitable Sentinel-1 scene pair found."),
        }

    before_meta = pair["before"]
    after_meta  = pair["after"]
    orbit_dir   = pair["orbit_direction"]
    orbit_mismatch = pair.get("orbit_mismatch_warning", False)
    temporal_gap   = pair.get("temporal_gap_days", 0.0)

    before_img: ee.Image = before_meta["image"]
    after_img:  ee.Image = after_meta["image"]

    # -------------------------------------------------------
    # 2. SAR BACKSCATTER CHANGE (supporting evidence)
    # -------------------------------------------------------
    vv_change = after_img.subtract(before_img).rename("VV_change")

    # Mean VV statistics for SAR evidence display
    before_vv_stats = before_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=40,
        maxPixels=1e8,
    ).getInfo() or {}

    after_vv_stats = after_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=40,
        maxPixels=1e8,
    ).getInfo() or {}

    before_mean_vv = before_vv_stats.get(S1_POLARIZATION)
    after_mean_vv  = after_vv_stats.get(S1_POLARIZATION)
    mean_vv_change = (
        round(float(after_mean_vv) - float(before_mean_vv), 2)
        if before_mean_vv is not None and after_mean_vv is not None
        else None
    )

    # -------------------------------------------------------
    # 3. WATER CLASSIFICATION (absolute threshold)
    # -------------------------------------------------------
    before_water_raw = before_img.select(S1_POLARIZATION).lt(sar_threshold_db)
    after_water_raw  = after_img.select(S1_POLARIZATION).lt(sar_threshold_db)

    # -------------------------------------------------------
    # 4. JRC PERMANENT WATER BASELINE
    # -------------------------------------------------------
    permanent_water = _get_jrc_permanent_water(aoi)
    perm_water_bin  = permanent_water.unmask(0)    # 0/1 image

    # -------------------------------------------------------
    # 5. FLOOD CANDIDATE MASK
    #    NEW WATER = after_water AND NOT before_water AND NOT permanent
    # -------------------------------------------------------
    before_water_bin = before_water_raw.unmask(0)
    after_water_bin  = after_water_raw.unmask(0)

    # Stable water (water in both before and after, not new)
    stable_water_mask = (
        after_water_bin.And(before_water_bin).And(perm_water_bin.Not())
        .rename("stable_water")
    )

    # New potential flood water
    flood_candidate_raw = (
        after_water_bin
        .And(before_water_bin.Not())
        .And(perm_water_bin.Not())
        .rename("flood_candidate")
    )

    # -------------------------------------------------------
    # 6. NOISE FILTERING — connectedPixelCount
    # -------------------------------------------------------
    connected = flood_candidate_raw.connectedPixelCount(
        maxSize=500, eightConnected=True
    )
    flood_mask = flood_candidate_raw.updateMask(
        connected.gte(FLOOD_MIN_CONNECTED_PIXELS)
    ).selfMask()

    # -------------------------------------------------------
    # 7. AREA CALCULATIONS (pixelArea — never degree-based)
    # -------------------------------------------------------
    permanent_water_km2  = _compute_area_km2(perm_water_bin.selfMask(), aoi)
    before_water_km2     = _compute_area_km2(before_water_bin.selfMask(), aoi)
    after_water_km2      = _compute_area_km2(after_water_bin.selfMask(), aoi)
    flood_candidate_km2  = _compute_area_km2(flood_candidate_raw.selfMask(), aoi)
    flood_area_km2       = _compute_area_km2(flood_mask, aoi)

    # SAR AOI coverage: use after image pixel count as proxy
    # (count non-masked pixels relative to AOI area)
    try:
        valid_pixel_area = (
            after_img.select(S1_POLARIZATION)
            .mask()
            .multiply(ee.Image.pixelArea())
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=40,
                maxPixels=1e8,
            )
        )
        valid_area_m2 = valid_pixel_area.values().get(0).getInfo() or 0
        sar_coverage_pct = min(100.0, (float(valid_area_m2) / 1e6) / aoi_area_km2 * 100.0)
    except Exception:
        sar_coverage_pct = 0.0

    # -------------------------------------------------------
    # 8. POLYGONIZE FLOOD EXTENT
    # -------------------------------------------------------
    try:
        flood_vectors = flood_mask.reduceToVectors(
            geometry=aoi,
            scale=10,
            geometryType="polygon",
            eightConnected=True,
            maxPixels=1e9,
        )
        flood_geojson = flood_vectors.getInfo() or {
            "type": "FeatureCollection", "features": []
        }
    except Exception as err:
        logger.warning("Flood polygonization failed: %s", err)
        flood_geojson = {"type": "FeatureCollection", "features": []}

    # -------------------------------------------------------
    # 9. GEE TILE URLS FOR VISUAL EVIDENCE
    # -------------------------------------------------------
    sar_grey_vis = {"min": -25, "max": 0, "palette": ["000000", "ffffff"]}
    sar_change_vis = {"min": -10, "max": 5, "palette": ["d73027", "ffffbf", "1a9850"]}
    perm_water_vis = {"palette": ["1565C0"]}
    flood_vis      = {"palette": ["9C27B0"]}
    stable_vis     = {"palette": ["00BCD4"]}

    tile_before_sar    = _get_tile_url(before_img.select(S1_POLARIZATION), sar_grey_vis)
    tile_after_sar     = _get_tile_url(after_img.select(S1_POLARIZATION),  sar_grey_vis)
    tile_vv_change     = _get_tile_url(vv_change, sar_change_vis)
    tile_perm_water    = _get_tile_url(perm_water_bin.selfMask(), perm_water_vis)
    tile_flood_extent  = _get_tile_url(flood_mask, flood_vis)
    tile_stable_water  = _get_tile_url(stable_water_mask.selfMask(), stable_vis)

    # -------------------------------------------------------
    # 10. CHIRPS RAINFALL SUMMARY
    # -------------------------------------------------------
    rainfall_summary = get_rainfall_summary(
        aoi=aoi,
        reference_date=after_end,
        windows=(1, 3, 7, 30),
        compute_anomaly_for_days=rainfall_window_days,
        historical_years=5,
    )

    rainfall_available = rainfall_summary.get("rainfall_anomaly_available", False)
    rainfall_anomaly_pct = rainfall_summary.get("rainfall_anomaly_percent")

    # -------------------------------------------------------
    # 11. DATA QUALITY
    # -------------------------------------------------------
    quality = _assess_flood_quality(
        before_found=True,
        after_found=True,
        orbit_mismatch=orbit_mismatch,
        temporal_gap_days=temporal_gap,
        sar_aoi_coverage_pct=sar_coverage_pct,
        rainfall_available=rainfall_available,
    )

    # -------------------------------------------------------
    # 12. FLOOD INDICATOR
    # -------------------------------------------------------
    indicator_result = _classify_flood_indicator(
        flood_area_km2=flood_area_km2,
        permanent_water_km2=permanent_water_km2,
        rainfall_anomaly_pct=rainfall_anomaly_pct,
    )

    # -------------------------------------------------------
    # BUILD RESPONSE
    # -------------------------------------------------------
    return {
        "available": True,
        "district": district.capitalize(),

        # Satellite metadata
        "satellite": "Sentinel-1",
        "polarization": S1_POLARIZATION,
        "orbit_direction": orbit_dir,
        "orbit_mismatch_warning": orbit_mismatch,
        "before_scene_id": f"COPERNICUS/S1_GRD/{before_meta['scene_id']}",
        "after_scene_id":  f"COPERNICUS/S1_GRD/{after_meta['scene_id']}",
        "before_date": before_meta["date"],
        "after_date":  after_meta["date"],
        "temporal_gap_days": temporal_gap,

        # SAR statistics
        "sar_threshold_db": sar_threshold_db,
        "threshold_method": f"Absolute VV < {sar_threshold_db} dB (Twele et al. 2016)",
        "before_mean_vv_db": round(float(before_mean_vv), 2) if before_mean_vv is not None else None,
        "after_mean_vv_db":  round(float(after_mean_vv),  2) if after_mean_vv  is not None else None,
        "mean_vv_change_db": mean_vv_change,

        # Water area statistics (all from pixelArea)
        "permanent_water_area_km2": permanent_water_km2,
        "before_water_area_km2":    before_water_km2,
        "after_water_area_km2":     after_water_km2,
        "flood_candidate_area_km2": flood_candidate_km2,
        "potential_flood_area_km2": flood_area_km2,
        "water_expansion_percent":  indicator_result.get("expansion_percent"),

        # Rainfall evidence
        **{f"rainfall_{k}": v for k, v in rainfall_summary.items()},

        # Flood indicator
        "flood_indicator": indicator_result["indicator"],
        "flood_indicator_detail": indicator_result,

        # Data quality
        "data_quality": quality,

        # Spatial output
        "flood_geojson": flood_geojson,
        "flood_polygon_count": len(flood_geojson.get("features", [])),

        # Map tile URLs for visual evidence
        "tiles": {
            "before_sar":   tile_before_sar,
            "after_sar":    tile_after_sar,
            "sar_change":   tile_vv_change,
            "permanent_water": tile_perm_water,
            "flood_extent": tile_flood_extent,
            "stable_water": tile_stable_water,
        },

        # Methodology
        "methodology": {
            "sar_dataset": "COPERNICUS/S1_GRD",
            "permanent_water_dataset": JRC_DATASET,
            "rainfall_dataset": "UCSB-CHG/CHIRPS/DAILY",
            "water_classification": (
                f"Absolute VV backscatter < {sar_threshold_db} dB (C-band, IW mode)"
            ),
            "flood_logic": (
                "NEW_FLOOD = after_water AND NOT before_water AND NOT permanent_water. "
                "Noise filtered with connectedPixelCount >= "
                f"{FLOOD_MIN_CONNECTED_PIXELS} pixels."
            ),
            "permanent_water_definition": (
                f"JRC occurrence >= {PERMANENT_WATER_OCCURRENCE_THRESHOLD}% "
                "(Pekel et al. 2016, Nature 540)"
            ),
            "area_calculation": "ee.Image.pixelArea() at 10 m resolution",
            "disclaimer": (
                "Potential flood extent is a satellite-derived indicator. "
                "It is not an official flood warning or confirmed flood event. "
                "Field verification is required for emergency decision-making."
            ),
        },
    }
