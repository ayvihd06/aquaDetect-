"""
test_drought_detection.py — Automated & Integration Tests for Drought Detection
=================================================================================

Tests:
1. Sentinel-2 spectral index & water extent computation.
2. Historical baseline window selection (same-season across past 5 years).
3. Water area anomaly, NDWI anomaly, NDVI anomaly, CHIRPS rainfall anomaly.
4. Deterministic drought indicator rules.
5. Unavailable data handling.
6. Real Madurai drought analysis integration test.
"""

import sys
import datetime
from app.services.hydrology.drought_detection import (
    analyze_drought,
    _classify_drought_indicator,
)
from app.services.change_detection import initialize_earth_engine


def test_gee_initialization():
    """Verify Earth Engine initializes cleanly."""
    print("Testing Earth Engine initialization...")
    initialize_earth_engine()
    print("  [OK] Earth Engine initialized")


def test_drought_indicator_classification():
    """Verify deterministic multi-pillar drought indicator rules."""
    print("Testing drought indicator rules...")
    res = _classify_drought_indicator(
        water_anomaly_pct=-55.0,
        ndwi_anomaly=-0.12,
        ndvi_anomaly_pct=-25.0,
        rainfall_30d_anomaly_pct=-40.0,
        rainfall_90d_anomaly_pct=-45.0,
    )
    assert res["indicator"] in ("CRITICAL", "HIGH")
    assert len(res["evidence_descriptions"]) >= 3

    res_norm = _classify_drought_indicator(
        water_anomaly_pct=5.0,
        ndwi_anomaly=0.01,
        ndvi_anomaly_pct=2.0,
        rainfall_30d_anomaly_pct=10.0,
        rainfall_90d_anomaly_pct=5.0,
    )
    assert res_norm["indicator"] == "NORMAL"
    print("  [OK] Drought indicator rules verified")


def test_future_drought_date_handling():
    """Verify requesting future date range is handled gracefully."""
    print("Testing future drought date handling...")
    future_start = (datetime.datetime.utcnow() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    future_end   = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")

    res = analyze_drought("Madurai", future_start, future_end)
    assert res["available"] is False
    assert "reason" in res
    print(f"  [OK] Handled future date safely: '{res['reason']}'")


def test_real_madurai_drought_detection():
    """Real Madurai Sentinel-2 & CHIRPS drought detection test."""
    print("Testing real Madurai Sentinel-2 & CHIRPS drought analysis...")
    res = analyze_drought(
        district="Madurai",
        current_start="2025-06-01",
        current_end="2025-08-31",
        season="jun_aug",
        historical_years_back=3,
    )
    assert res["available"] is True
    assert res["satellite"] == "Sentinel-2"
    assert "COPERNICUS/S2" in res["current_image_id"]
    assert res["current_water_km2"] >= 0.0
    assert "drought_indicator" in res
    assert res["data_quality"]["status"] in ("HIGH", "MEDIUM", "LOW")
    print(f"  [OK] Madurai Drought Analysis complete:")
    print(f"    - Current image ID: {res['current_image_id']} ({res['current_date']})")
    print(f"    - Historical years: {res['historical_years_used']}")
    print(f"    - Water area:       {res['current_water_km2']} km² (anomaly: {res['water_area_anomaly_percent']}%)")
    print(f"    - Indicator:        {res['drought_indicator']}")


if __name__ == "__main__":
    print("=== RUNNING DROUGHT DETECTION TESTS ===")
    test_gee_initialization()
    test_drought_indicator_classification()
    test_future_drought_date_handling()
    test_real_madurai_drought_detection()
    print("=== ALL DROUGHT DETECTION TESTS PASSED SUCCESSFULLY! ===")
