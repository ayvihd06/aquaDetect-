"""
drought_detection.py — Real Drought Monitoring for AquaDetect
==============================================================

Calculates evidence-based drought indicators using:

1. Water area anomaly: Sentinel-2 NDWI water extent vs. same-season historical.
   (Reuses compare_water_extent_ee infrastructure — no duplication.)

2. NDWI anomaly: mean NDWI current vs. historical baseline.

3. NDVI anomaly: Sentinel-2 NDVI current vs. historical baseline.
   (NDVI = (B8 - B4) / (B8 + B4))

4. Rainfall anomaly: CHIRPS 30-day and 90-day windows.

All four are shown separately. No arbitrary single score.
Indicator is derived from documented rules in hydrology_config.py.

IMPORTANT: No dummy values. If a component is unavailable, return
    {"available": False, "reason": "..."} for that component.

Scientific terminology:
    Potential Drought Conditions / Drought Indicator / Environmental Stress
    NOT "Official Drought Declaration".
"""

import logging
import datetime
from typing import Dict, Any, Optional, List

import ee

from app.services.hydrology.hydrology_config import (
    DROUGHT_WATER_ANOMALY_MODERATE,
    DROUGHT_WATER_ANOMALY_HIGH,
    DROUGHT_WATER_ANOMALY_CRITICAL,
    DROUGHT_NDWI_ANOMALY_MODERATE,
    DROUGHT_NDWI_ANOMALY_HIGH,
    DROUGHT_NDVI_ANOMALY_MODERATE,
    DROUGHT_NDVI_ANOMALY_HIGH,
    DROUGHT_RAINFALL_ANOMALY_MODERATE,
    DROUGHT_RAINFALL_ANOMALY_HIGH,
    DROUGHT_MIN_PILLARS_FOR_HIGH,
    DROUGHT_MIN_PILLARS_FOR_MODERATE,
    DROUGHT_HISTORICAL_YEARS_BACK,
    SEASON_DATE_RANGES,
    QUALITY_HIGH_COVERAGE,
    QUALITY_MEDIUM_COVERAGE,
)
from app.services.hydrology.rainfall_service import (
    get_chirps_rainfall,
    get_chirps_historical_baseline,
    compute_rainfall_anomaly_percent,
)

# Reuse existing GEE utilities — no duplication
from app.services.change_detection import (
    initialize_earth_engine,
    get_district_aoi,
    get_sentinel2_observation,
    apply_cloud_shadow_mask,
)

logger = logging.getLogger(__name__)


# ===========================================================
# SPECTRAL INDEX COMPUTATION
# ===========================================================

def _compute_s2_indices(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    max_cloud: float = 20.0,
) -> Dict[str, Any]:
    """
    Retrieve Sentinel-2 observation and compute NDWI + NDVI statistics.

    Returns:
        {
          "available": True,
          "ndwi_mean": float,
          "ndvi_mean": float,
          "image_id": str,
          "date": str,
          "cloud_cover": float,
        }
    or {"available": False, "reason": str}
    """
    obs = get_sentinel2_observation(aoi, start_date, end_date, max_cloud)
    if not obs.get("found"):
        return {
            "available": False,
            "reason": obs.get("error", f"No Sentinel-2 observation found {start_date}–{end_date}."),
        }

    raw_image = obs["raw_image"]
    masked    = apply_cloud_shadow_mask(raw_image)
    valid_mask = masked.select("valid_mask")

    ndwi = masked.normalizedDifference(["B3", "B8"]).rename("NDWI").updateMask(valid_mask)
    ndvi = masked.normalizedDifference(["B8", "B4"]).rename("NDVI").updateMask(valid_mask)

    stats = ndwi.addBands(ndvi).reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=20,
        maxPixels=1e9,
    ).getInfo() or {}

    ndwi_mean = stats.get("NDWI")
    ndvi_mean = stats.get("NDVI")

    if ndwi_mean is None and ndvi_mean is None:
        return {
            "available": False,
            "reason": "Sentinel-2 spectral statistics returned no valid pixels.",
        }

    return {
        "available": True,
        "ndwi_mean": round(float(ndwi_mean), 4) if ndwi_mean is not None else None,
        "ndvi_mean": round(float(ndvi_mean), 4) if ndvi_mean is not None else None,
        "image_id": obs["image_id"],
        "date": obs["date"],
        "cloud_cover": obs["cloud_cover"],
    }


# ===========================================================
# HISTORICAL INDEX BASELINE (same-season, multiple years)
# ===========================================================

def _compute_historical_s2_baseline(
    aoi: ee.Geometry,
    current_start: str,
    current_end: str,
    years_back: int = DROUGHT_HISTORICAL_YEARS_BACK,
    max_cloud: float = 30.0,
) -> Dict[str, Any]:
    """
    Compute NDWI and NDVI historical baseline for the same calendar window
    over the past `years_back` years.

    Returns:
        {
          "available": True,
          "historical_ndwi_mean": float,
          "historical_ndvi_mean": float,
          "years_used": [int, ...],
          "year_values": {year: {ndwi, ndvi}, ...},
        }
    or {"available": False, "reason": str}
    """
    start_dt = datetime.datetime.strptime(current_start, "%Y-%m-%d")
    end_dt   = datetime.datetime.strptime(current_end,   "%Y-%m-%d")

    ndwi_vals: Dict[int, float] = {}
    ndvi_vals: Dict[int, float] = {}
    year_details: Dict[int, Dict] = {}

    for offset in range(1, years_back + 1):
        hist_year = start_dt.year - offset
        try:
            h_start = start_dt.replace(year=hist_year).strftime("%Y-%m-%d")
            h_end   = end_dt.replace(year=hist_year).strftime("%Y-%m-%d")
        except ValueError:
            # Feb 29 → Feb 28 in non-leap years
            h_start = start_dt.replace(year=hist_year, day=28).strftime("%Y-%m-%d")
            h_end   = end_dt.replace(year=hist_year, day=28).strftime("%Y-%m-%d")

        result = _compute_s2_indices(aoi, h_start, h_end, max_cloud)
        if result.get("available"):
            if result.get("ndwi_mean") is not None:
                ndwi_vals[hist_year] = result["ndwi_mean"]
            if result.get("ndvi_mean") is not None:
                ndvi_vals[hist_year] = result["ndvi_mean"]
            year_details[hist_year] = {
                "ndwi": result.get("ndwi_mean"),
                "ndvi": result.get("ndvi_mean"),
                "image_id": result.get("image_id"),
                "date": result.get("date"),
            }

    if not ndwi_vals and not ndvi_vals:
        return {
            "available": False,
            "reason": (
                f"Insufficient historical Sentinel-2 observations: "
                f"0 of {years_back} years available."
            ),
        }

    hist_ndwi = (
        round(sum(ndwi_vals.values()) / len(ndwi_vals), 4)
        if ndwi_vals else None
    )
    hist_ndvi = (
        round(sum(ndvi_vals.values()) / len(ndvi_vals), 4)
        if ndvi_vals else None
    )

    return {
        "available": True,
        "historical_ndwi_mean": hist_ndwi,
        "historical_ndvi_mean": hist_ndvi,
        "years_used": sorted(set(list(ndwi_vals.keys()) + list(ndvi_vals.keys()))),
        "year_values": year_details,
    }


# ===========================================================
# WATER AREA HISTORICAL BASELINE (Sentinel-2 NDWI)
# ===========================================================

def _compute_water_area_baseline(
    aoi: ee.Geometry,
    current_start: str,
    current_end: str,
    threshold: float = 0.30,
    years_back: int = DROUGHT_HISTORICAL_YEARS_BACK,
    max_cloud: float = 30.0,
) -> Dict[str, Any]:
    """
    Compute current water area and historical baseline water area.

    Returns:
        {
          "available": True,
          "current_water_km2": float,
          "historical_water_km2": float,
          "water_area_anomaly_percent": float,
          "current_date": str,
          "current_image_id": str,
          "years_used": [int, ...],
        }
    """
    # Current
    current_obs = get_sentinel2_observation(aoi, current_start, current_end, max_cloud)
    if not current_obs.get("found"):
        return {
            "available": False,
            "reason": f"No current Sentinel-2 observation: {current_obs.get('error', '')}",
        }

    def water_km2(obs_result: Dict) -> Optional[float]:
        if not obs_result.get("found"):
            return None
        img = obs_result["image"]
        ndwi = img.select("NDWI")
        valid = img.select("valid_mask")
        water_mask = ndwi.gte(threshold).And(valid).selfMask()
        reduced = (
            water_mask.multiply(ee.Image.pixelArea())
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=10,
                maxPixels=1e9,
            )
        )
        val = reduced.values().get(0).getInfo()
        return round(float(val or 0.0) / 1_000_000.0, 4) if val is not None else None

    current_km2 = water_km2(current_obs)
    if current_km2 is None:
        return {
            "available": False,
            "reason": "Could not compute current water area from Sentinel-2.",
        }

    # Historical baseline
    start_dt = datetime.datetime.strptime(current_start, "%Y-%m-%d")
    end_dt   = datetime.datetime.strptime(current_end,   "%Y-%m-%d")
    hist_areas: Dict[int, float] = {}

    for offset in range(1, years_back + 1):
        hist_year = start_dt.year - offset
        try:
            h_start = start_dt.replace(year=hist_year).strftime("%Y-%m-%d")
            h_end   = end_dt.replace(year=hist_year).strftime("%Y-%m-%d")
        except ValueError:
            h_start = start_dt.replace(year=hist_year, day=28).strftime("%Y-%m-%d")
            h_end   = end_dt.replace(year=hist_year, day=28).strftime("%Y-%m-%d")

        h_obs = get_sentinel2_observation(aoi, h_start, h_end, max_cloud)
        h_km2 = water_km2(h_obs) if h_obs.get("found") else None
        if h_km2 is not None:
            hist_areas[hist_year] = h_km2

    if not hist_areas:
        return {
            "available": True,
            "current_water_km2": current_km2,
            "historical_water_km2": None,
            "water_area_anomaly_percent": None,
            "current_date": current_obs["date"],
            "current_image_id": current_obs["image_id"],
            "years_used": [],
            "historical_unavailable_reason": "Insufficient historical Sentinel-2 observations.",
        }

    hist_mean = round(sum(hist_areas.values()) / len(hist_areas), 4)
    anomaly = (
        round(((current_km2 - hist_mean) / hist_mean) * 100.0, 1)
        if hist_mean > 0 else None
    )

    return {
        "available": True,
        "current_water_km2": current_km2,
        "historical_water_km2": hist_mean,
        "historical_year_values_km2": hist_areas,
        "water_area_anomaly_percent": anomaly,
        "current_date": current_obs["date"],
        "current_image_id": current_obs["image_id"],
        "years_used": sorted(hist_areas.keys()),
    }


# ===========================================================
# DROUGHT INDICATOR CLASSIFICATION
# ===========================================================

def _classify_drought_indicator(
    water_anomaly_pct: Optional[float],
    ndwi_anomaly: Optional[float],
    ndvi_anomaly_pct: Optional[float],
    rainfall_30d_anomaly_pct: Optional[float],
    rainfall_90d_anomaly_pct: Optional[float],
) -> Dict[str, Any]:
    """
    Classify drought indicator based on independent evidence pillars.
    All thresholds from hydrology_config.py.

    Each pillar is classified independently:
        HIGH / MODERATE / LOW / NEUTRAL / UNKNOWN

    Overall indicator:
        CRITICAL  = >= DROUGHT_MIN_PILLARS_FOR_HIGH pillars at HIGH
        HIGH      = most available pillars at HIGH or MODERATE
        MODERATE  = >= DROUGHT_MIN_PILLARS_FOR_MODERATE pillars at MODERATE+
        LOW       = weak evidence
        NORMAL    = no significant anomaly detected
        INSUFFICIENT_DATA = < 2 pillars available
    """
    pillars: Dict[str, str] = {}
    evidence_descriptions: List[str] = []

    # --- Water area ---
    if water_anomaly_pct is not None:
        if water_anomaly_pct <= DROUGHT_WATER_ANOMALY_CRITICAL:
            pillars["water_area"] = "CRITICAL"
            evidence_descriptions.append(
                f"Water extent {water_anomaly_pct:.0f}% below historical (CRITICAL)"
            )
        elif water_anomaly_pct <= DROUGHT_WATER_ANOMALY_HIGH:
            pillars["water_area"] = "HIGH"
            evidence_descriptions.append(
                f"Water extent {water_anomaly_pct:.0f}% below historical (HIGH)"
            )
        elif water_anomaly_pct <= DROUGHT_WATER_ANOMALY_MODERATE:
            pillars["water_area"] = "MODERATE"
            evidence_descriptions.append(
                f"Water extent {water_anomaly_pct:.0f}% below historical (MODERATE)"
            )
        else:
            pillars["water_area"] = "LOW"
            evidence_descriptions.append(
                f"Water extent anomaly {water_anomaly_pct:.0f}% (within normal range)"
            )
    else:
        pillars["water_area"] = "UNKNOWN"

    # --- NDWI ---
    if ndwi_anomaly is not None:
        if ndwi_anomaly <= DROUGHT_NDWI_ANOMALY_HIGH:
            pillars["ndwi"] = "HIGH"
            evidence_descriptions.append(f"NDWI anomaly {ndwi_anomaly:+.3f} (HIGH dryness)")
        elif ndwi_anomaly <= DROUGHT_NDWI_ANOMALY_MODERATE:
            pillars["ndwi"] = "MODERATE"
            evidence_descriptions.append(f"NDWI anomaly {ndwi_anomaly:+.3f} (MODERATE dryness)")
        else:
            pillars["ndwi"] = "LOW"
            evidence_descriptions.append(f"NDWI anomaly {ndwi_anomaly:+.3f} (within normal range)")
    else:
        pillars["ndwi"] = "UNKNOWN"

    # --- NDVI ---
    if ndvi_anomaly_pct is not None:
        if ndvi_anomaly_pct <= DROUGHT_NDVI_ANOMALY_HIGH:
            pillars["ndvi"] = "HIGH"
            evidence_descriptions.append(
                f"NDVI {ndvi_anomaly_pct:.0f}% below historical (HIGH vegetation stress)"
            )
        elif ndvi_anomaly_pct <= DROUGHT_NDVI_ANOMALY_MODERATE:
            pillars["ndvi"] = "MODERATE"
            evidence_descriptions.append(
                f"NDVI {ndvi_anomaly_pct:.0f}% below historical (MODERATE vegetation stress)"
            )
        else:
            pillars["ndvi"] = "LOW"
    else:
        pillars["ndvi"] = "UNKNOWN"

    # --- Rainfall 30-day ---
    if rainfall_30d_anomaly_pct is not None:
        if rainfall_30d_anomaly_pct <= DROUGHT_RAINFALL_ANOMALY_HIGH:
            pillars["rainfall_30d"] = "HIGH"
            evidence_descriptions.append(
                f"30-day rainfall {rainfall_30d_anomaly_pct:.0f}% below historical (HIGH deficit)"
            )
        elif rainfall_30d_anomaly_pct <= DROUGHT_RAINFALL_ANOMALY_MODERATE:
            pillars["rainfall_30d"] = "MODERATE"
            evidence_descriptions.append(
                f"30-day rainfall {rainfall_30d_anomaly_pct:.0f}% below historical (MODERATE deficit)"
            )
        else:
            pillars["rainfall_30d"] = "LOW"
    else:
        pillars["rainfall_30d"] = "UNKNOWN"

    # --- Rainfall 90-day ---
    if rainfall_90d_anomaly_pct is not None:
        if rainfall_90d_anomaly_pct <= DROUGHT_RAINFALL_ANOMALY_HIGH:
            pillars["rainfall_90d"] = "HIGH"
            evidence_descriptions.append(
                f"90-day rainfall {rainfall_90d_anomaly_pct:.0f}% below historical"
            )
        elif rainfall_90d_anomaly_pct <= DROUGHT_RAINFALL_ANOMALY_MODERATE:
            pillars["rainfall_90d"] = "MODERATE"
        else:
            pillars["rainfall_90d"] = "LOW"
    else:
        pillars["rainfall_90d"] = "UNKNOWN"

    # Count available + severity
    available_pillars = [k for k, v in pillars.items() if v != "UNKNOWN"]
    critical_count  = sum(1 for v in pillars.values() if v == "CRITICAL")
    high_count      = sum(1 for v in pillars.values() if v in ("HIGH", "CRITICAL"))
    moderate_count  = sum(1 for v in pillars.values() if v in ("MODERATE", "HIGH", "CRITICAL"))

    if len(available_pillars) < 2:
        indicator = "INSUFFICIENT_DATA"
    elif critical_count >= 2:
        indicator = "CRITICAL"
    elif high_count >= DROUGHT_MIN_PILLARS_FOR_HIGH:
        indicator = "HIGH"
    elif moderate_count >= DROUGHT_MIN_PILLARS_FOR_MODERATE:
        indicator = "MODERATE"
    elif moderate_count >= 1:
        indicator = "LOW"
    else:
        indicator = "NORMAL"

    return {
        "indicator": indicator,
        "pillar_levels": pillars,
        "available_pillars": available_pillars,
        "evidence_descriptions": evidence_descriptions,
        "methodology_note": (
            "Drought indicator derived from independent satellite and climate evidence pillars. "
            "Not an official drought declaration. Field verification recommended."
        ),
    }


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
# MAIN DROUGHT ANALYSIS FUNCTION
# ===========================================================

def analyze_drought(
    district: str,
    current_start: str,
    current_end: str,
    season: str = "same_season",
    historical_years_back: int = DROUGHT_HISTORICAL_YEARS_BACK,
    ndwi_threshold: float = 0.30,
) -> Dict[str, Any]:
    """
    Perform real multi-indicator drought analysis for a district.

    Analyzes:
      1. Water area anomaly (Sentinel-2 NDWI water extent)
      2. NDWI anomaly (mean spectral index)
      3. NDVI anomaly (vegetation stress indicator)
      4. 30-day CHIRPS rainfall anomaly
      5. 90-day CHIRPS rainfall anomaly

    Seasonal comparability:
      Same calendar window used for all historical baselines.

    Returns:
        Full structured result or {"available": False, "reason": "..."}.
    """
    initialize_earth_engine()

    aoi = get_district_aoi(district)

    # -------------------------------------------------------
    # 1. WATER AREA ANOMALY (Sentinel-2)
    # -------------------------------------------------------
    water_result = _compute_water_area_baseline(
        aoi, current_start, current_end,
        threshold=ndwi_threshold,
        years_back=historical_years_back,
    )

    current_water_km2      = water_result.get("current_water_km2")
    historical_water_km2   = water_result.get("historical_water_km2")
    water_anomaly_pct      = water_result.get("water_area_anomaly_percent")
    current_date           = water_result.get("current_date")
    current_image_id       = water_result.get("current_image_id")
    water_years_used       = water_result.get("years_used", [])

    # -------------------------------------------------------
    # 2. NDWI + NDVI ANOMALY (Sentinel-2)
    # -------------------------------------------------------
    current_indices = _compute_s2_indices(aoi, current_start, current_end)
    historical_indices = _compute_historical_s2_baseline(
        aoi, current_start, current_end, historical_years_back
    )

    current_ndwi = current_indices.get("ndwi_mean") if current_indices.get("available") else None
    current_ndvi = current_indices.get("ndvi_mean") if current_indices.get("available") else None

    historical_ndwi = historical_indices.get("historical_ndwi_mean") if historical_indices.get("available") else None
    historical_ndvi = historical_indices.get("historical_ndvi_mean") if historical_indices.get("available") else None

    ndwi_anomaly = (
        round(current_ndwi - historical_ndwi, 4)
        if current_ndwi is not None and historical_ndwi is not None
        else None
    )
    ndvi_anomaly_pct = (
        round(((current_ndvi - historical_ndvi) / abs(historical_ndvi)) * 100.0, 1)
        if current_ndvi is not None and historical_ndvi is not None and historical_ndvi != 0
        else None
    )

    # -------------------------------------------------------
    # 3. CHIRPS RAINFALL ANOMALY (30-day and 90-day)
    # -------------------------------------------------------
    rain_30d_obs  = get_chirps_rainfall(aoi, current_end, 30)
    rain_90d_obs  = get_chirps_rainfall(aoi, current_end, 90)
    rain_30d_base = get_chirps_historical_baseline(aoi, current_end, 30, historical_years_back)
    rain_90d_base = get_chirps_historical_baseline(aoi, current_end, 90, historical_years_back)

    rain_30d_mm        = rain_30d_obs.get("rainfall_mm")  if rain_30d_obs.get("available")  else None
    rain_30d_hist_mm   = rain_30d_base.get("historical_mean_mm") if rain_30d_base.get("available") else None
    rain_30d_anomaly   = compute_rainfall_anomaly_percent(rain_30d_mm, rain_30d_hist_mm) if rain_30d_mm is not None and rain_30d_hist_mm else None

    rain_90d_mm        = rain_90d_obs.get("rainfall_mm")  if rain_90d_obs.get("available")  else None
    rain_90d_hist_mm   = rain_90d_base.get("historical_mean_mm") if rain_90d_base.get("available") else None
    rain_90d_anomaly   = compute_rainfall_anomaly_percent(rain_90d_mm, rain_90d_hist_mm) if rain_90d_mm is not None and rain_90d_hist_mm else None

    # -------------------------------------------------------
    # 4. GENERATE TILE URLS
    # -------------------------------------------------------
    tiles: Dict[str, str] = {}
    if current_indices.get("available") and water_result.get("available"):
        try:
            obs_result = get_sentinel2_observation(aoi, current_start, current_end, 30.0)
            if obs_result.get("found"):
                raw = obs_result["raw_image"]
                masked = apply_cloud_shadow_mask(raw)
                valid  = masked.select("valid_mask")
                ndwi_img = masked.normalizedDifference(["B3", "B8"]).updateMask(valid)
                ndvi_img = masked.normalizedDifference(["B8", "B4"]).updateMask(valid)
                water_mask = ndwi_img.gte(ndwi_threshold).selfMask()

                tiles["current_rgb"]   = _get_tile_url(
                    raw.select(["B4", "B3", "B2"]),
                    {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}
                )
                tiles["current_ndwi"]  = _get_tile_url(
                    ndwi_img,
                    {"min": -0.2, "max": 0.6, "palette": ["000000", "8B4513", "FFFF00", "00FFFF", "0000FF"]}
                )
                tiles["current_ndvi"]  = _get_tile_url(
                    ndvi_img,
                    {"min": -0.1, "max": 0.8, "palette": ["8B4513", "FFFF00", "00FF00"]}
                )
                tiles["current_water"] = _get_tile_url(
                    water_mask,
                    {"palette": ["1565C0"]}
                )
        except Exception as te:
            logger.warning("Tile URL generation for drought skipped: %s", te)

    # -------------------------------------------------------
    # 5. DROUGHT INDICATOR CLASSIFICATION
    # -------------------------------------------------------
    if not water_result.get("available") and not current_indices.get("available"):
        return {
            "available": False,
            "reason": "Insufficient Sentinel-2 data to perform drought analysis.",
        }

    indicator_result = _classify_drought_indicator(
        water_anomaly_pct=water_anomaly_pct,
        ndwi_anomaly=ndwi_anomaly,
        ndvi_anomaly_pct=ndvi_anomaly_pct,
        rainfall_30d_anomaly_pct=rain_30d_anomaly,
        rainfall_90d_anomaly_pct=rain_90d_anomaly,
    )

    # -------------------------------------------------------
    # 6. DATA QUALITY
    # -------------------------------------------------------
    available_pillars = indicator_result.get("available_pillars", [])
    if len(available_pillars) >= 4:
        dq_status = "HIGH"
    elif len(available_pillars) >= 2:
        dq_status = "MEDIUM"
    else:
        dq_status = "LOW"

    # -------------------------------------------------------
    # BUILD RESPONSE
    # -------------------------------------------------------
    return {
        "available": True,
        "district": district.capitalize(),
        "analysis_period": {
            "current_start": current_start,
            "current_end": current_end,
            "season": season,
            "historical_years_back": historical_years_back,
        },

        # Sentinel-2 metadata
        "satellite": "Sentinel-2",
        "current_date": current_date,
        "current_image_id": current_image_id,
        "current_cloud_cover": current_indices.get("cloud_cover") if current_indices.get("available") else None,
        "historical_years_used": sorted(
            set(water_years_used + (historical_indices.get("years_used") or []))
        ),

        # Water area indicators
        "current_water_km2": current_water_km2,
        "historical_water_km2": historical_water_km2,
        "water_area_anomaly_percent": water_anomaly_pct,
        "water_area_available": water_result.get("available", False),
        "water_area_historical_year_values": water_result.get("historical_year_values_km2"),

        # NDWI indicators
        "current_ndwi_mean": current_ndwi,
        "historical_ndwi_mean": historical_ndwi,
        "ndwi_anomaly": ndwi_anomaly,
        "ndwi_available": (current_ndwi is not None and historical_ndwi is not None),

        # NDVI indicators
        "current_ndvi_mean": current_ndvi,
        "historical_ndvi_mean": historical_ndvi,
        "ndvi_anomaly_percent": ndvi_anomaly_pct,
        "ndvi_available": (current_ndvi is not None and historical_ndvi is not None),

        # Rainfall indicators
        "rainfall_30d_mm": rain_30d_mm,
        "rainfall_30d_historical_mm": rain_30d_hist_mm,
        "rainfall_30d_anomaly_percent": rain_30d_anomaly,
        "rainfall_30d_available": rain_30d_obs.get("available", False),
        "rainfall_90d_mm": rain_90d_mm,
        "rainfall_90d_historical_mm": rain_90d_hist_mm,
        "rainfall_90d_anomaly_percent": rain_90d_anomaly,
        "rainfall_90d_available": rain_90d_obs.get("available", False),
        "rainfall_historical_years": rain_30d_base.get("years_used") if rain_30d_base.get("available") else None,

        # Drought indicator
        "drought_indicator": indicator_result["indicator"],
        "drought_indicator_detail": indicator_result,

        # Data quality
        "data_quality": {
            "status": dq_status,
            "available_evidence_pillars": available_pillars,
            "total_evidence_pillars": 5,
            "warnings": (
                ["Interpret with caution — limited data available."]
                if dq_status == "LOW" else []
            ),
        },

        # Tile URLs
        "tiles": tiles,

        # Methodology
        "methodology": {
            "satellite_dataset": "COPERNICUS/S2_SR_HARMONIZED",
            "rainfall_dataset": "UCSB-CHG/CHIRPS/DAILY",
            "ndwi_formula": "NDWI = (B3 - B8) / (B3 + B8)",
            "ndvi_formula": "NDVI = (B8 - B4) / (B8 + B4)",
            "seasonal_comparison": "Same calendar window used for historical baseline",
            "disclaimer": (
                "Drought monitoring indicators are satellite-derived environmental "
                "indicators intended for monitoring and decision support. "
                "They do not constitute an official drought declaration."
            ),
        },
    }
