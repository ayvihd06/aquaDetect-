"""
hydrology.py — Flood & Drought Monitoring API Routes for AquaDetect
====================================================================

New routes (does NOT modify any existing routes):
    POST /water/flood-analysis
    POST /water/drought-analysis

These routes call real GEE-based services.
No dummy values are ever returned.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator

from app.services.hydrology.flood_detection import (
    analyze_flood,
    FLOOD_SAR_THRESHOLD_DB,
)
from app.services.hydrology.drought_detection import analyze_drought
from app.services.hydrology.hydrology_config import DROUGHT_HISTORICAL_YEARS_BACK

logger = logging.getLogger(__name__)

router = APIRouter()


# ===========================================================
# REQUEST MODELS
# ===========================================================

class FloodRequest(BaseModel):
    """
    Flood analysis request.

    before_start / before_end: pre-event date window (inclusive).
    after_start  / after_end:  post-event date window (inclusive).
    rainfall_window_days: CHIRPS window for rainfall anomaly (1/3/7/30).
    sar_threshold_db: VV backscatter threshold — defaults to FLOOD_SAR_THRESHOLD_DB
                      (-16.0 dB per hydrology_config.py).
                      Not exposed in the normal UI; available for scientific/advanced use.
    """
    district: str
    before_start: str                             # "2026-07-01"
    before_end: str                               # "2026-07-31"
    after_start: str                              # "2026-08-01"
    after_end: str                                # "2026-08-12"
    rainfall_window_days: int = 7
    sar_threshold_db: float = FLOOD_SAR_THRESHOLD_DB   # -16.0 dB consistent default

    @validator("rainfall_window_days")
    def validate_rainfall_window(cls, v):
        if v not in (1, 3, 7, 30):
            raise ValueError("rainfall_window_days must be 1, 3, 7, or 30.")
        return v

    @validator("sar_threshold_db")
    def validate_sar_threshold(cls, v):
        if not (-30.0 <= v <= -5.0):
            raise ValueError(
                "sar_threshold_db must be between -30.0 and -5.0 dB. "
                f"Default is {FLOOD_SAR_THRESHOLD_DB} dB."
            )
        return v


class DroughtRequest(BaseModel):
    """
    Drought analysis request.

    season: Used to label the analysis period. Seasonal comparison
            uses the same calendar window for historical baselines.
    historical_years_back: Number of historical years for baseline.
    """
    district: str
    current_start: str            # "2026-06-01"
    current_end: str              # "2026-08-12"
    season: str = "jun_aug"       # "jun_aug" | "sep_nov" | "dec_feb" | "mar_may" | "full_year"
    historical_years_back: int = DROUGHT_HISTORICAL_YEARS_BACK

    @validator("historical_years_back")
    def validate_years(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("historical_years_back must be between 1 and 10.")
        return v


# ===========================================================
# FLOOD ANALYSIS
# ===========================================================

@router.post("/water/flood-analysis")
def flood_analysis(request: FloodRequest):
    """
    Real Sentinel-1 SAR flood detection with CHIRPS rainfall evidence.

    Algorithm:
    1. Find before/after Sentinel-1 GRD IW VV scene pair (same orbit direction).
    2. Classify water-like pixels using absolute VV < threshold.
    3. Apply JRC permanent water baseline.
    4. Flood candidates = after_water AND NOT before_water AND NOT permanent.
    5. Noise-filter with connectedPixelCount.
    6. Area calculation with pixelArea().
    7. Generate GEE tile URLs for visual evidence.
    8. CHIRPS rainfall anomaly.
    9. FLOOD INDICATOR per hydrology_config.py thresholds.

    If Sentinel-1 data is unavailable → returns {"available": False, "reason": "..."}.
    Never returns fabricated values.
    """
    if not request.district.strip():
        raise HTTPException(
            status_code=422,
            detail="District name is required."
        )

    if request.before_start >= request.before_end:
        raise HTTPException(
            status_code=422,
            detail="before_start must be before before_end."
        )

    if request.after_start >= request.after_end:
        raise HTTPException(
            status_code=422,
            detail="after_start must be before after_end."
        )

    if request.before_end > request.after_start:
        raise HTTPException(
            status_code=422,
            detail=(
                "Before period must end before after period starts. "
                "Overlapping date ranges are not supported."
            )
        )

    try:
        result = analyze_flood(
            district=request.district,
            before_start=request.before_start,
            before_end=request.before_end,
            after_start=request.after_start,
            after_end=request.after_end,
            rainfall_window_days=request.rainfall_window_days,
            sar_threshold_db=request.sar_threshold_db,
        )
        return result

    except HTTPException:
        raise
    except Exception as err:
        logger.error("Flood analysis failed: %s", err, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Flood analysis failed: {str(err)}",
        )


# ===========================================================
# DROUGHT ANALYSIS
# ===========================================================

@router.post("/water/drought-analysis")
def drought_analysis(request: DroughtRequest):
    """
    Real multi-indicator drought analysis using Sentinel-2 and CHIRPS.

    Evidence pillars (each shown independently):
    1. Water area anomaly (Sentinel-2 NDWI water extent vs historical baseline).
    2. NDWI anomaly (spectral index current vs historical).
    3. NDVI anomaly (vegetation stress indicator).
    4. 30-day CHIRPS rainfall anomaly.
    5. 90-day CHIRPS rainfall anomaly.

    Historical baseline: same calendar window for each of the past
    `historical_years_back` years.

    DROUGHT INDICATOR derived from hydrology_config.py thresholds only.
    Not an official drought declaration.

    If Sentinel-2 data is unavailable → returns {"available": False, "reason": "..."}.
    Never returns fabricated values.
    """
    if not request.district.strip():
        raise HTTPException(
            status_code=422,
            detail="District name is required."
        )

    if request.current_start >= request.current_end:
        raise HTTPException(
            status_code=422,
            detail="current_start must be before current_end."
        )

    try:
        result = analyze_drought(
            district=request.district,
            current_start=request.current_start,
            current_end=request.current_end,
            season=request.season,
            historical_years_back=request.historical_years_back,
        )
        return result

    except HTTPException:
        raise
    except Exception as err:
        logger.error("Drought analysis failed: %s", err, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Drought analysis failed: {str(err)}",
        )
