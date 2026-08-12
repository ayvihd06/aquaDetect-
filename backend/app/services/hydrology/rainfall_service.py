"""
rainfall_service.py — CHIRPS Rainfall Integration for AquaDetect
=================================================================

Provides real CHIRPS-derived rainfall statistics via Google Earth Engine.

CHIRPS = Climate Hazards Group InfraRed Precipitation with Station data
Dataset: UCSB-CHG/CHIRPS/DAILY
Reference: Funk et al. (2015), Scientific Data 2, 150066

IMPORTANT: Never substitute dummy values.
If data is unavailable, return {"available": False, "reason": "..."}.
"""

import logging
import datetime
from typing import Dict, Any, Optional, List

import ee

from app.services.hydrology.hydrology_config import (
    CHIRPS_COLLECTION,
    CHIRPS_BASELINE_YEARS,
)

logger = logging.getLogger(__name__)


# ===========================================================
# CHIRPS RAINFALL — SINGLE PERIOD
# ===========================================================

def get_chirps_rainfall(
    aoi: ee.Geometry,
    end_date: str,
    days: int,
) -> Dict[str, Any]:
    """
    Compute total CHIRPS rainfall (mm) over the AOI for `days` preceding end_date.

    Returns:
        {
          "available": True,
          "rainfall_mm": float,
          "start_date": str,
          "end_date": str,
          "days": int,
          "pixel_count": int,
        }
    or:
        {"available": False, "reason": str}
    """
    try:
        end_dt  = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - datetime.timedelta(days=days)
        start_str = start_dt.strftime("%Y-%m-%d")

        # CHIRPS has ~2-week preliminary lag; final data lags ~1 month.
        today = datetime.datetime.utcnow()
        if end_dt > today:
            return {
                "available": False,
                "reason": f"End date {end_date} is in the future — CHIRPS data not yet available.",
            }

        collection = (
            ee.ImageCollection(CHIRPS_COLLECTION)
            .filterBounds(aoi)
            .filterDate(start_str, end_date)
            .select("precipitation")
        )

        count = collection.size().getInfo()
        if count == 0:
            return {
                "available": False,
                "reason": (
                    f"No CHIRPS observations found between {start_str} and {end_date}."
                ),
            }

        # Sum daily precipitation over the period
        total_precip = collection.sum()

        stats = total_precip.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=5566,          # CHIRPS native ~5 km resolution
            maxPixels=1e8,
        ).getInfo() or {}

        rainfall_mm = stats.get("precipitation")
        if rainfall_mm is None:
            return {
                "available": False,
                "reason": "CHIRPS reduction returned no valid pixels over AOI.",
            }

        return {
            "available": True,
            "rainfall_mm": round(float(rainfall_mm), 2),
            "start_date": start_str,
            "end_date": end_date,
            "days": days,
            "scene_count": count,
        }

    except Exception as error:
        logger.warning("CHIRPS rainfall retrieval failed: %s", error)
        return {
            "available": False,
            "reason": f"CHIRPS data retrieval failed: {str(error)}",
        }


# ===========================================================
# CHIRPS HISTORICAL BASELINE — SAME PERIOD, MULTIPLE YEARS
# ===========================================================

def get_chirps_historical_baseline(
    aoi: ee.Geometry,
    end_date: str,
    days: int,
    years_back: int = CHIRPS_BASELINE_YEARS,
) -> Dict[str, Any]:
    """
    Compute mean CHIRPS rainfall for the same calendar window
    over the past `years_back` years.

    Uses the same month-day range anchored to `end_date` for each
    historical year to ensure seasonal comparability.

    Returns:
        {
          "available": True,
          "historical_mean_mm": float,
          "years_used": [int, ...],
          "year_values_mm": {year: mm, ...},
          "baseline_window_days": int,
        }
    or:
        {"available": False, "reason": str}
    """
    try:
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        today  = datetime.datetime.utcnow()

        year_values: Dict[int, float] = {}
        missing_years: List[int] = []

        for offset in range(1, years_back + 1):
            hist_end_year = end_dt.year - offset

            # Handle leap-year edge (Feb 29 → Feb 28)
            try:
                hist_end_dt = end_dt.replace(year=hist_end_year)
            except ValueError:
                hist_end_dt = end_dt.replace(year=hist_end_year, day=28)

            hist_start_dt = hist_end_dt - datetime.timedelta(days=days)

            # Skip years where data cannot yet be available
            if hist_end_dt > today:
                missing_years.append(hist_end_year)
                continue

            hist_end_str   = hist_end_dt.strftime("%Y-%m-%d")
            hist_start_str = hist_start_dt.strftime("%Y-%m-%d")

            collection = (
                ee.ImageCollection(CHIRPS_COLLECTION)
                .filterBounds(aoi)
                .filterDate(hist_start_str, hist_end_str)
                .select("precipitation")
            )

            count = collection.size().getInfo()
            if count < max(1, days // 3):   # require at least 1/3 of days
                missing_years.append(hist_end_year)
                continue

            total = collection.sum()
            stats = total.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=aoi,
                scale=5566,
                maxPixels=1e8,
            ).getInfo() or {}

            val = stats.get("precipitation")
            if val is not None:
                year_values[hist_end_year] = round(float(val), 2)
            else:
                missing_years.append(hist_end_year)

        if len(year_values) < 2:
            return {
                "available": False,
                "reason": (
                    f"Insufficient historical CHIRPS data: only {len(year_values)} "
                    f"of {years_back} requested years available."
                ),
            }

        mean_mm = round(sum(year_values.values()) / len(year_values), 2)

        return {
            "available": True,
            "historical_mean_mm": mean_mm,
            "years_used": sorted(year_values.keys()),
            "year_values_mm": year_values,
            "baseline_window_days": days,
        }

    except Exception as error:
        logger.warning("CHIRPS historical baseline failed: %s", error)
        return {
            "available": False,
            "reason": f"CHIRPS historical baseline retrieval failed: {str(error)}",
        }


# ===========================================================
# RAINFALL ANOMALY CALCULATION
# ===========================================================

def compute_rainfall_anomaly_percent(
    observed_mm: float,
    historical_mean_mm: float,
) -> Optional[float]:
    """
    Calculate signed rainfall anomaly relative to historical baseline.

    Returns % anomaly (positive = wetter than normal, negative = drier).
    Returns None if historical_mean_mm is 0 or invalid.
    """
    if historical_mean_mm is None or historical_mean_mm <= 0:
        return None
    return round(((observed_mm - historical_mean_mm) / historical_mean_mm) * 100.0, 1)


# ===========================================================
# MULTI-WINDOW RAINFALL SUMMARY
# ===========================================================

def get_rainfall_summary(
    aoi: ee.Geometry,
    reference_date: str,
    windows: tuple = (1, 3, 7, 30),
    compute_anomaly_for_days: int = 7,
    historical_years: int = CHIRPS_BASELINE_YEARS,
) -> Dict[str, Any]:
    """
    Fetch CHIRPS rainfall for multiple time windows and compute anomaly.

    Args:
        aoi: Earth Engine geometry.
        reference_date: The "after" date (YYYY-MM-DD) for rainfall calculation.
        windows: Tuple of day windows to compute.
        compute_anomaly_for_days: Which window to use for anomaly (default 7).
        historical_years: Years of baseline data.

    Returns:
        Dict with per-window rainfall values and anomaly if available.
    """
    result: Dict[str, Any] = {}

    for days in windows:
        key = f"rainfall_{days}d"
        rain = get_chirps_rainfall(aoi, reference_date, days)
        if rain["available"]:
            result[key] = rain["rainfall_mm"]
            result[f"{key}_available"] = True
        else:
            result[key] = None
            result[f"{key}_available"] = False
            result[f"{key}_unavailable_reason"] = rain.get("reason")

    # Anomaly for selected window
    anomaly_key = f"rainfall_{compute_anomaly_for_days}d"
    observed = result.get(anomaly_key)
    result["anomaly_window_days"] = compute_anomaly_for_days

    if observed is not None:
        baseline = get_chirps_historical_baseline(
            aoi, reference_date, compute_anomaly_for_days, historical_years
        )
        if baseline["available"]:
            result["historical_rainfall_mm"] = baseline["historical_mean_mm"]
            result["historical_years_used"] = baseline["years_used"]
            result["historical_year_values_mm"] = baseline["year_values_mm"]
            result["rainfall_anomaly_percent"] = compute_rainfall_anomaly_percent(
                observed, baseline["historical_mean_mm"]
            )
            result["rainfall_anomaly_available"] = True
        else:
            result["historical_rainfall_mm"] = None
            result["rainfall_anomaly_percent"] = None
            result["rainfall_anomaly_available"] = False
            result["rainfall_anomaly_unavailable_reason"] = baseline.get("reason")
    else:
        result["historical_rainfall_mm"] = None
        result["rainfall_anomaly_percent"] = None
        result["rainfall_anomaly_available"] = False

    return result
