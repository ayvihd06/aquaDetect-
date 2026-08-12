"""
Test Change Detection API & Tile URL Generation
"""
import sys
from app.services.change_detection import compare_water_extent_ee

def main():
    print("Testing Earth Engine Water Change Detection & Tile URL Generation for Madurai...")
    res = compare_water_extent_ee(
        district="Madurai",
        comparison_type="same_season",
        before_year=2023,
        after_year=2026,
        season="jun_aug",
        max_cloud_cover=20.0,
        threshold=0.30,
    )
    
    print("\n--- RESULTS SUMMARY ---")
    print(f"Success: {res.get('success')}")
    if not res.get("success"):
        print(f"Error: {res.get('error')}")
        sys.exit(1)

    print(f"District: {res['analysis']['district']}")
    print(f"Before Date ({res['before']['date']}): Total {res['before']['water_area_km2']} km² | Comparable: {res['before']['comparable_water_area_km2']} km² (Coverage: {res['before']['valid_coverage_percent']}%)")
    print(f"After Date  ({res['after']['date']}): Total {res['after']['water_area_km2']} km² | Comparable: {res['after']['comparable_water_area_km2']} km² (Coverage: {res['after']['valid_coverage_percent']}%)")
    print(f"Net Change: {res['change']['net_change_km2']} km² ({res['change']['change_percent']}%)")
    print(f"Loss: {res['change']['loss_area_km2']} km² ({res['regions']['loss_count']} regions)")
    print(f"Gain: {res['change']['gain_area_km2']} km² ({res['regions']['gain_count']} regions)")
    print(f"Stable: {res['change']['stable_area_km2']} km² ({res['regions']['stable_count']} regions)")
    print(f"No Data Area: {res['change']['no_data_area_km2']} km²")
    print(f"Data Quality Status: {res['quality']['status']} ({res['quality']['comparison_valid_coverage_percent']}% coverage)")
    print(f"Disclaimer: {res['quality']['disclaimer']}")

    # Mathematical Conservation Check
    loss_plus_stable = round(res['change']['loss_area_km2'] + res['change']['stable_area_km2'], 4)
    gain_plus_stable = round(res['change']['gain_area_km2'] + res['change']['stable_area_km2'], 4)

    print("\n--- MATHEMATICAL CONSERVATION CHECK ---")
    print(f"Loss ({res['change']['loss_area_km2']}) + Stable ({res['change']['stable_area_km2']}) = {loss_plus_stable} km² (Before Comparable: {res['before']['comparable_water_area_km2']} km²)")
    print(f"Gain ({res['change']['gain_area_km2']}) + Stable ({res['change']['stable_area_km2']}) = {gain_plus_stable} km² (After Comparable: {res['after']['comparable_water_area_km2']} km²)")

    # Tile URLs check
    tiles = res.get("tiles", {})
    print("\n--- GENERATED GEE TILE URLS ---")
    print(f"Before RGB Tile:  {tiles.get('before_rgb')}")
    print(f"After RGB Tile:   {tiles.get('after_rgb')}")
    print(f"Before NDWI Tile: {tiles.get('before_ndwi')}")
    print(f"After NDWI Tile:  {tiles.get('after_ndwi')}")
    print(f"Before Mask Tile: {tiles.get('before_mask')}")
    print(f"After Mask Tile:  {tiles.get('after_mask')}")
    print(f"Loss Mask Tile:   {tiles.get('loss_mask')}")
    print(f"Gain Mask Tile:   {tiles.get('gain_mask')}")
    print(f"Stable Mask Tile: {tiles.get('stable_mask')}")

    assert tiles.get("before_rgb"), "Before RGB Tile URL missing!"
    assert tiles.get("after_rgb"), "After RGB Tile URL missing!"
    assert tiles.get("before_ndwi"), "Before NDWI Tile URL missing!"
    assert tiles.get("after_ndwi"), "After NDWI Tile URL missing!"
    print("\nAll verification assertions passed!")

if __name__ == "__main__":
    main()
