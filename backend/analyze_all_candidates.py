"""
Server-side Batch Evaluation of Sentinel-2 Scenes over District AOI
"""
import ee
from app.services.change_detection import initialize_earth_engine, get_district_aoi, apply_cloud_shadow_mask

def batch_evaluate(district: str, start_date: str, end_date: str, max_cloud: float = 30.0):
    initialize_earth_engine()
    aoi = get_district_aoi(district)
    aoi_area = (aoi.area().getInfo() or 1.0)

    print(f"\n=======================================================")
    print(f"BATCH EVALUATION FOR {district.upper()} ({start_date} to {end_date})")
    print(f"=======================================================")

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    pixel_area = ee.Image.pixelArea()

    def calc_coverage(img):
        masked = apply_cloud_shadow_mask(img)
        valid = masked.select("valid_mask")
        valid_m2 = (
            valid.selfMask()
            .multiply(pixel_area)
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=30,
                maxPixels=1e9,
            )
            .get("valid_mask")
        )
        valid_m2_safe = ee.Algorithms.If(valid_m2, valid_m2, 0.0)
        cov_pct = ee.Number(valid_m2_safe).divide(aoi_area).multiply(100.0)
        
        # SCL histogram
        scl_hist = img.select("SCL").reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=aoi,
            scale=30,
            maxPixels=1e9,
        ).get("SCL")

        return img.set({
            "aoi_valid_coverage_pct": cov_pct,
            "scl_histogram": scl_hist,
        })

    eval_col = col.map(calc_coverage)
    
    # Get metadata of top 10 scenes
    feature_list = eval_col.reduceColumns(
        ee.Reducer.toList(4),
        ["system:index", "system:time_start", "CLOUDY_PIXEL_PERCENTAGE", "aoi_valid_coverage_pct"]
    ).get("list").getInfo()

    import datetime
    scenes = []
    for item in feature_list:
        img_id, ts, granule_cloud, aoi_valid = item
        date_str = datetime.datetime.fromtimestamp(ts / 1000.0, datetime.timezone.utc).strftime("%Y-%m-%d")
        scenes.append({
            "id": img_id,
            "date": date_str,
            "granule_cloud": round(float(granule_cloud or 0.0), 2),
            "aoi_valid_pct": round(float(aoi_valid or 0.0), 1),
        })

    # Sort by AOI valid coverage percentage descending
    scenes_sorted = sorted(scenes, key=lambda x: x["aoi_valid_pct"], reverse=True)

    print(f"Evaluated {len(scenes)} scenes:")
    for rank, s in enumerate(scenes_sorted, 1):
        print(f"  Rank #{rank}: Date {s['date']} | AOI Valid Coverage: {s['aoi_valid_pct']}% | Granule Cloud: {s['granule_cloud']}% | ID: {s['id']}")

    return scenes_sorted

if __name__ == "__main__":
    print("\n--- 2023 BEFORE PERIOD (Jun-Aug) ---")
    batch_evaluate("Madurai", "2023-06-01", "2023-08-31", 30.0)

    print("\n--- 2026 AFTER PERIOD (Jun-Aug) ---")
    batch_evaluate("Madurai", "2026-06-01", "2026-08-31", 30.0)
