"""
Threshold Sensitivity & Diagnostic Testing for NDWI Water Classification
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services.ndwi_service import inspect_raster_bands, process_ndwi_image

TIF_PATH = "../sample_sentinel2.tif"

def main():
    print("\n==================================================")
    print("NDWI THRESHOLD SENSITIVITY & DIAGNOSTIC TEST")
    print("==================================================")

    with open(TIF_PATH, "rb") as f:
        file_bytes = f.read()

    info = inspect_raster_bands(file_bytes)
    green_band = info["auto_green"] or 1
    nir_band   = info["auto_nir"] or 2

    print(f"Sample GeoTIFF info: {info['band_count']} bands, CRS={info['crs']}")
    print(f"Bands used: Green={green_band}, NIR={nir_band}\n")

    thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]

    for th in thresholds:
        res = process_ndwi_image(
            file_bytes=file_bytes,
            threshold=th,
            green_band=green_band,
            nir_band=nir_band,
            debug=True,
        )

        st = res["statistics"]
        dbg = res.get("debug_info", {})

        print(f"Threshold: {th:.2f} | Polygons: {st['water_body_count']:2d} | Total Area: {st['total_water_area_km2']:.4f} km² | Water Pixels: {st['water_pixels']:6d} ({st['water_pixel_percentage']:.2f}%)")
        print(f"   NDWI Stats -> Min: {st['ndwi_min']:.4f}, Max: {st['ndwi_max']:.4f}, Mean: {st['ndwi_mean']:.4f}, Median: {st['ndwi_median']:.4f}")
        print(f"   Raw vs Cleaned Pixels: {dbg.get('raw_water_pixels')} -> {dbg.get('cleaned_water_pixels')} (Components before size filter: {dbg.get('components_before_filter')})")
        print("-" * 75)

if __name__ == "__main__":
    main()
