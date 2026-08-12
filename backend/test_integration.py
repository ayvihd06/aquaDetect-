"""
Integration Test — Full NDWI Pipeline with Scientific Validation Fields
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services.ndwi_service import inspect_raster_bands, process_ndwi_image

TIF_PATH = "../sample_sentinel2.tif"

def check(condition, label):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    return condition

def main():
    with open(TIF_PATH, "rb") as f:
        file_bytes = f.read()

    info = inspect_raster_bands(file_bytes)
    green = info["auto_green"]
    nir   = info["auto_nir"]

    print("\n=== TEST 1: Manual Threshold (0.30) ===")
    res = process_ndwi_image(file_bytes=file_bytes, threshold=0.30, green_band=green, nir_band=nir, debug=True)

    check(res["success"], "success == True")
    check(res["satellite_source"] == "Sentinel-2 Surface Reflectance Harmonized", "satellite_source correct")
    check(res["spatial_resolution_m"] == 10, "spatial_resolution_m == 10")
    check(res["threshold_method"] == "manual", "threshold_method == manual")
    check(res["selected_threshold"] == 0.30, "selected_threshold == 0.30")
    check("ndwi_threshold" in res, "ndwi_threshold backwards-compat key present")
    s = res["statistics"]
    check(s["ndwi_min"] is not None, "ndwi_min present")
    check(s["ndwi_max"] is not None, "ndwi_max present")
    check(s["ndwi_mean"] is not None, "ndwi_mean present")
    check(s["ndwi_median"] is not None, "ndwi_median present")
    check(s["ndwi_std"] is not None, "ndwi_std present")
    check(s["valid_pixel_percentage"] > 0, "valid_pixel_percentage > 0")
    check(s["cloud_shadow_percentage"] >= 0, "cloud_shadow_percentage >= 0")
    check(s["water_pixel_percentage"] >= 0, "water_pixel_percentage >= 0")
    check("detection_quality" in s, "detection_quality present")
    check(s["detection_quality"] in ("HIGH", "MEDIUM", "LOW"), "detection_quality valid value")
    vf = res["validation_flags"]
    check("review_required" in vf, "validation_flags.review_required present")
    check("disclaimer" in vf, "validation_flags.disclaimer present")
    check("Sentinel-2 derived surface-water extent" in vf["disclaimer"], "disclaimer contains correct scientific label")
    check("spatial_resolution_m" not in res["geojson"]["features"][0]["properties"] or
          res["geojson"]["features"][0]["properties"].get("spatial_resolution_m") == 10, "feature spatial_resolution_m == 10")
    check(res["geojson"]["features"][0]["properties"]["source"] == "Sentinel-2 derived surface-water extent", "feature source label correct")
    di = res.get("debug_info", {})
    check("raw_water_pixels" in di, "debug_info.raw_water_pixels present")
    check("cleaned_water_pixels" in di, "debug_info.cleaned_water_pixels present")
    check("components_after_opening" in di, "debug_info.components_after_opening present")
    check(di["raw_water_pixels"] >= di["cleaned_water_pixels"], "cleaned <= raw (cleaning never adds pixels)")

    print(f"\n  Results: {s['water_body_count']} water bodies | {s['total_water_area_km2']} km² | Quality: {s['detection_quality']}")
    print(f"  NDWI: min={s['ndwi_min']} max={s['ndwi_max']} mean={s['ndwi_mean']} median={s['ndwi_median']}")
    print(f"  Valid pixels: {s['valid_pixel_percentage']}% | Cloud/shadow: {s['cloud_shadow_percentage']}%")

    print("\n=== TEST 2: Adaptive (Otsu) Threshold ===")
    res2 = process_ndwi_image(file_bytes=file_bytes, threshold=0.30, green_band=green, nir_band=nir,
                               threshold_mode="adaptive", debug=True)
    check(res2["success"], "success == True")
    check(res2["threshold_method"] in ("adaptive_otsu", "manual_fallback"), "threshold_method is valid")
    ti = res2["threshold_info"]
    check("otsu_threshold" in ti, "otsu_threshold in threshold_info")
    check("fallback_reason" in ti, "fallback_reason in threshold_info")
    print(f"  Threshold method: {res2['threshold_method']} | Selected: {res2['selected_threshold']} | Otsu raw: {ti['otsu_threshold']}")
    if ti.get("fallback_reason"):
        print(f"  Fallback reason: {ti['fallback_reason']}")

    print("\n=== TEST 3: Empty mask (threshold=0.99) ===")
    res3 = process_ndwi_image(file_bytes=file_bytes, threshold=0.99, green_band=green, nir_band=nir)
    check(res3["success"], "success == True (empty result is still success)")
    check(res3["statistics"]["water_body_count"] == 0, "water_body_count == 0 at threshold 0.99")
    check(len(res3["geojson"]["features"]) == 0, "no features at threshold 0.99")
    check("ndwi_min" in res3["statistics"], "ndwi stats still present in empty result")

    print("\n=== ALL TESTS COMPLETE ===")

if __name__ == "__main__":
    main()
