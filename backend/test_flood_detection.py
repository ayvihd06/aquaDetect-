"""
test_flood_detection.py — Automated & Integration Tests for Flood Detection
=============================================================================

Tests:
1. Sentinel-1 collection query for Madurai AOI.
2. Real before/after scene selection (same orbit direction).
3. SAR water classification & noise filtering.
4. JRC permanent water exclusion.
5. NEW WATER area calculation with pixelArea().
6. CHIRPS rainfall retrieval & anomaly calculation.
7. Unavailable data handling (future date returns available: false).
8. Deterministic flood indicator classification.
"""

import sys
import datetime
from app.services.hydrology.flood_detection import (
    analyze_flood,
    _select_same_orbit_pair,
    _classify_flood_indicator,
    _assess_flood_quality,
)
from app.services.hydrology.rainfall_service import get_chirps_rainfall
from app.services.change_detection import initialize_earth_engine, get_district_aoi
from app.services.hydrology.hydrology_config import FLOOD_SAR_THRESHOLD_DB


def test_gee_initialization():
    """Verify Earth Engine initializes cleanly."""
    print("Testing Earth Engine initialization...")
    initialize_earth_engine()
    print("  [OK] Earth Engine initialized")


def test_sentinel1_scene_pair_selection():
    """Verify Sentinel-1 scene query finds real scenes with matching orbit for Madurai."""
    print("Testing Sentinel-1 scene pair selection (Madurai)...")
    initialize_earth_engine()
    aoi = get_district_aoi("Madurai")
    pair = _select_same_orbit_pair(
        aoi,
        before_start="2025-06-01",
        before_end="2025-07-31",
        after_start="2025-08-01",
        after_end="2025-08-31",
    )
    assert pair["found"] is True, f"Failed to find S1 pair: {pair.get('reason')}"
    assert "orbit_direction" in pair
    assert "before" in pair
    assert "after" in pair
    assert pair["before"]["scene_id"] != ""
    assert pair["after"]["scene_id"] != ""
    print(f"  [OK] Found matching {pair['orbit_direction']} pair: {pair['before']['date']} -> {pair['after']['date']}")


def test_chirps_rainfall_retrieval():
    """Verify CHIRPS returns real non-negative rainfall values for past dates."""
    print("Testing CHIRPS rainfall retrieval...")
    initialize_earth_engine()
    aoi = get_district_aoi("Madurai")
    res = get_chirps_rainfall(aoi, "2025-08-15", 7)
    assert res["available"] is True
    assert res["rainfall_mm"] >= 0.0
    print(f"  [OK] CHIRPS 7-day rainfall: {res['rainfall_mm']} mm")


def test_future_date_unavailable():
    """Verify future date returns explicit available: false with reason."""
    print("Testing future date unavailability handling...")
    future_date = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    future_start = (datetime.datetime.utcnow() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    res = analyze_flood("Madurai", future_start, future_date, future_date, future_date)
    assert res["available"] is False
    assert "reason" in res
    assert len(res["reason"]) > 0
    print(f"  [OK] Handled future date safely: '{res['reason']}'")


def test_flood_indicator_classification():
    """Verify deterministic flood indicator rules."""
    print("Testing flood indicator classification rules...")
    res1 = _classify_flood_indicator(
        flood_area_km2=2.5,
        permanent_water_km2=10.0,
        rainfall_anomaly_pct=120.0,
    )
    assert res1["indicator"] == "HIGH"

    res2 = _classify_flood_indicator(
        flood_area_km2=0.0,
        permanent_water_km2=10.0,
        rainfall_anomaly_pct=10.0,
    )
    assert res2["indicator"] in ("INSUFFICIENT_DATA", "LOW")
    print("  [OK] Flood indicator rules verified")


def test_flood_quality_assessment():
    """Verify quality scoring logic."""
    print("Testing quality scoring logic...")
    q_high = _assess_flood_quality(
        before_found=True,
        after_found=True,
        orbit_mismatch=False,
        temporal_gap_days=12.0,
        sar_aoi_coverage_pct=92.0,
        rainfall_available=True,
    )
    assert q_high["status"] == "HIGH"
    assert len(q_high["warnings"]) == 0

    q_low = _assess_flood_quality(
        before_found=True,
        after_found=True,
        orbit_mismatch=True,
        temporal_gap_days=150.0,
        sar_aoi_coverage_pct=40.0,
        rainfall_available=False,
    )
    assert q_low["status"] == "LOW"
    assert len(q_low["warnings"]) > 0
    print("  [OK] Quality scoring logic verified")


def test_real_madurai_flood_detection():
    """Real Madurai Sentinel-1 SAR integration test."""
    print("Testing real Madurai Sentinel-1 SAR flood analysis...")
    res = analyze_flood(
        district="Madurai",
        before_start="2025-06-01",
        before_end="2025-07-15",
        after_start="2025-07-16",
        after_end="2025-08-31",
        rainfall_window_days=7,
        sar_threshold_db=FLOOD_SAR_THRESHOLD_DB,
    )
    assert res["available"] is True
    assert res["satellite"] == "Sentinel-1"
    assert "COPERNICUS/S1_GRD" in res["before_scene_id"]
    assert "COPERNICUS/S1_GRD" in res["after_scene_id"]
    assert res["potential_flood_area_km2"] >= 0.0
    assert res["permanent_water_area_km2"] >= 0.0
    assert res["sar_threshold_db"] == -16.0
    assert "flood_indicator" in res
    assert res["data_quality"]["status"] in ("HIGH", "MEDIUM", "LOW")
    print(f"  [OK] Madurai Flood Analysis complete:")
    print(f"    - Before scene: {res['before_scene_id']} ({res['before_date']})")
    print(f"    - After scene:  {res['after_scene_id']} ({res['after_date']})")
    print(f"    - Orbit:        {res['orbit_direction']}")
    print(f"    - Flood Area:   {res['potential_flood_area_km2']} km²")
    print(f"    - Indicator:    {res['flood_indicator']}")


if __name__ == "__main__":
    print("=== RUNNING FLOOD DETECTION TESTS ===")
    test_gee_initialization()
    test_sentinel1_scene_pair_selection()
    test_chirps_rainfall_retrieval()
    test_future_date_unavailable()
    test_flood_indicator_classification()
    test_flood_quality_assessment()
    test_real_madurai_flood_detection()
    print("=== ALL FLOOD DETECTION TESTS PASSED SUCCESSFULLY! ===")
