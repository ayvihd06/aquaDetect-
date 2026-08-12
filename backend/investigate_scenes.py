"""
Investigate Sentinel-2 Scene Coverage & SCL Class Breakdown over Madurai
"""
import sys
import ee
from app.services.change_detection import initialize_earth_engine, get_district_aoi, apply_cloud_shadow_mask

def analyze_period(district: str, start_date: str, end_date: str, max_cloud_cover: float = 30.0):
    initialize_earth_engine()
    aoi = get_district_aoi(district)
    aoi_area_m2 = aoi.area().getInfo()
    aoi_area_km2 = aoi_area_m2 / 1_000_000.0

    print(f"\n=======================================================")
    print(f"ANALYZING SENTINEL-2 SCENES FOR {district.upper()}")
    print(f"Period: {start_date} to {end_date} (Max Scene Cloud: {max_cloud_cover}%)")
    print(f"AOI Area: {aoi_area_km2:.2f} km²")
    print(f"=======================================================")

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    img_list = collection.toList(collection.size())
    count = img_list.size().getInfo()
    print(f"Total scenes found in Earth Engine: {count}\n")

    best_valid_pct = -1.0
    best_scene_info = None

    for i in range(count):
        img = ee.Image(img_list.get(i))
        img_id = img.get("system:index").getInfo()
        timestamp = img.get("system:time_start").getInfo()
        scene_cloud_pct = img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

        import datetime
        date_str = datetime.datetime.utcfromtimestamp(timestamp / 1000.0).strftime("%Y-%m-%d")

        # SCL breakdown over AOI
        scl = img.select("SCL")
        masked_img = apply_cloud_shadow_mask(img)
        valid_mask = masked_img.select("valid_mask")

        # Calculate valid area over AOI
        pixel_area = ee.Image.pixelArea()
        valid_area_m2 = (
            valid_mask.selfMask()
            .multiply(pixel_area)
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=10,
                maxPixels=1e9,
            )
            .get("valid_mask")
            .getInfo()
        ) or 0.0

        valid_area_km2 = valid_area_m2 / 1_000_000.0
        valid_pct = round((valid_area_km2 / aoi_area_km2) * 100.0, 1)

        print(f"[{i+1}/{count}] Date: {date_str} | ID: {img_id}")
        print(f"      Scene-wide Cloud %: {scene_cloud_pct:.2f}% | AOI Valid Coverage: {valid_pct}% ({valid_area_km2:.2f} km²)")

        # SCL Histogram over AOI
        scl_hist = (
            scl.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram(),
                geometry=aoi,
                scale=10,
                maxPixels=1e9,
            )
            .get("SCL")
            .getInfo()
        ) or {}

        scl_class_names = {
            "0": "NO_DATA", "1": "SATURATED", "2": "CAST_SHADOWS", "3": "CLOUD_SHADOWS",
            "4": "VEGETATION", "5": "NOT_VEGETATED", "6": "WATER", "7": "UNCLASSIFIED",
            "8": "CLOUD_MEDIUM_PROB", "9": "CLOUD_HIGH_PROB", "10": "THIN_CIRRUS", "11": "SNOW"
        }
        
        scl_summary = []
        for code, name in scl_class_names.items():
            if code in scl_hist:
                cnt = scl_hist[code]
                scl_summary.append(f"{name}({code}): {cnt}")
        print(f"      SCL Pixel Classes in AOI: {', '.join(scl_summary)}")
        print("-" * 65)

        if valid_pct > best_valid_pct:
            best_valid_pct = valid_pct
            best_scene_info = {
                "id": img_id,
                "date": date_str,
                "scene_cloud_pct": scene_cloud_pct,
                "aoi_valid_pct": valid_pct,
                "scl_hist": scl_hist,
            }

    print(f"\n🏆 BEST SCENE FOR AOI COVERAGE:")
    if best_scene_info:
        print(f"   Date: {best_scene_info['date']} (ID: {best_scene_info['id']})")
        print(f"   AOI Valid Coverage: {best_scene_info['aoi_valid_pct']}% (Scene Cloud %: {best_scene_info['scene_cloud_pct']:.2f}%)")
    else:
        print("   No suitable scene found!")

if __name__ == "__main__":
    district = "Madurai"
    print("--- INVESTIGATING BEFORE PERIOD (2023 Jun-Aug) ---")
    analyze_period(district, "2023-06-01", "2023-08-31", max_cloud_cover=30.0)

    print("\n--- INVESTIGATING AFTER PERIOD (2026 Jun-Aug) ---")
    analyze_period(district, "2026-06-01", "2026-08-31", max_cloud_cover=30.0)
