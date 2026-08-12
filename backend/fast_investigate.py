"""
Fast Sentinel-2 Candidate Scene AOI Coverage Analysis
"""
import ee
from app.services.change_detection import initialize_earth_engine, get_district_aoi, apply_cloud_shadow_mask

def evaluate_period(district: str, start_date: str, end_date: str, max_cloud_cover: float = 30.0):
    initialize_earth_engine()
    aoi = get_district_aoi(district)
    aoi_area_km2 = (aoi.area().getInfo() or 1.0) / 1_000_000.0

    print(f"\n=======================================================")
    print(f"DISTRICT: {district.upper()} ({start_date} to {end_date})")
    print(f"AOI Area: {aoi_area_km2:.2f} km²")
    print(f"=======================================================")

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    img_list = collection.toList(15)
    count = img_list.size().getInfo()
    print(f"Found {count} candidate scenes with granule cloud < {max_cloud_cover}%\n")

    results = []
    pixel_area = ee.Image.pixelArea()

    for i in range(count):
        img = ee.Image(img_list.get(i))
        img_id = img.get("system:index").getInfo()
        timestamp = img.get("system:time_start").getInfo()
        granule_cloud = img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()

        import datetime
        date_str = datetime.datetime.fromtimestamp(timestamp / 1000.0, datetime.timezone.utc).strftime("%Y-%m-%d")

        masked = apply_cloud_shadow_mask(img)
        valid_mask = masked.select("valid_mask")

        # Reduce region for valid area
        valid_m2 = (
            valid_mask.selfMask()
            .multiply(pixel_area)
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=20,  # 20m scale for rapid analysis
                maxPixels=1e9,
            )
            .get("valid_mask")
            .getInfo()
        ) or 0.0

        valid_km2 = valid_m2 / 1_000_000.0
        valid_pct = round((valid_km2 / aoi_area_km2) * 100.0, 1)

        # SCL class breakdown over AOI
        scl = img.select("SCL")
        scl_hist = (
            scl.reduceRegion(
                reducer=ee.Reducer.frequencyHistogram(),
                geometry=aoi,
                scale=20,
                maxPixels=1e9,
            )
            .get("SCL")
            .getInfo()
        ) or {}

        results.append({
            "index": i + 1,
            "id": img_id,
            "date": date_str,
            "granule_cloud": granule_cloud,
            "valid_pct": valid_pct,
            "valid_km2": valid_km2,
            "scl_hist": scl_hist,
        })

        print(f"[{i+1}/{count}] Date: {date_str} | Granule Cloud: {granule_cloud:.2f}% | AOI Valid: {valid_pct}% ({valid_km2:.2f} km²)")
        print(f"      SCL Classes in AOI: {scl_hist}")

    # Sort results by valid_pct descending
    results.sort(key=lambda x: x["valid_pct"], reverse=True)
    best = results[0] if results else None

    print("\n-------------------------------------------------------")
    print(f"RANKED CANDIDATE SCENES BY AOI VALID COVERAGE:")
    for r in results:
        print(f"  Rank #{results.index(r)+1}: Date {r['date']} -> AOI Valid Coverage: {r['valid_pct']}% (Granule Cloud: {r['granule_cloud']:.2f}%)")

    if best:
        print(f"\n✅ WINNING SCENE FOR {district} ({start_date[:4]}): {best['date']} with {best['valid_pct']}% AOI coverage")

if __name__ == "__main__":
    evaluate_period("Madurai", "2023-06-01", "2023-08-31", max_cloud_cover=30.0)
    evaluate_period("Madurai", "2026-06-01", "2026-08-31", max_cloud_cover=30.0)
