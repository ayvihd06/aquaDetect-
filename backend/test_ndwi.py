"""
Quick test for the NDWI service using the sample Sentinel-2 GeoTIFF.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.ndwi_service import inspect_raster_bands, process_ndwi_image

TIF_PATH = "../sample_sentinel2.tif"

print()
print("=" * 50)
print("NDWI Service Test")
print("=" * 50)


# -------------------------------------------------------
# Step 1: Inspect bands
# -------------------------------------------------------

print("\n[1] Inspecting bands...")

with open(TIF_PATH, "rb") as f:
    file_bytes = f.read()

info = inspect_raster_bands(file_bytes)

print(f"    Band count : {info['band_count']}")
for b in info["bands"]:
    print(f"    Band {b['index']:2d}: description={b['description']!r:20s}  color_interp={b['color_interp']}")

print(f"    Auto Green : {info['auto_green']}")
print(f"    Auto NIR   : {info['auto_nir']}")
print(f"    Auto detect: {info['auto_detected']}")


# -------------------------------------------------------
# Step 2: Pick bands
# -------------------------------------------------------

if info["auto_detected"]:
    green_band = info["auto_green"]
    nir_band   = info["auto_nir"]
    print(f"\n[2] Using auto-detected bands: Green={green_band}, NIR={nir_band}")
else:
    # For a 2-band file, fall back to 1 and 2 only for testing purposes
    green_band = 1
    nir_band   = 2
    print(f"\n[2] Bands not auto-detected. Using band 1=Green, 2=NIR for test.")


# -------------------------------------------------------
# Step 3: Run NDWI
# -------------------------------------------------------

print("\n[3] Running NDWI detection (threshold=0.30)...")

result = process_ndwi_image(
    file_bytes=file_bytes,
    threshold=0.30,
    green_band=green_band,
    nir_band=nir_band,
)

print(f"    success          : {result['success']}")
print(f"    detection_method : {result['detection_method']}")
print(f"    ndwi_threshold   : {result['ndwi_threshold']}")

stats = result["statistics"]
print()
print("Statistics:")
print(f"    water_body_count       : {stats['water_body_count']}")
print(f"    total_water_area_km2   : {stats['total_water_area_km2']}")
print(f"    largest_water_body_km2 : {stats['largest_water_body_km2']}")
print(f"    average_water_body_km2 : {stats['average_water_body_km2']}")

features = result["geojson"]["features"]
print(f"\nGeoJSON features returned: {len(features)}")
if features:
    sample = features[0]["properties"]
    print(f"Sample feature properties: {sample}")

print()
print("=" * 50)
print("Test PASSED" if result["success"] else "Test FAILED")
print("=" * 50)
