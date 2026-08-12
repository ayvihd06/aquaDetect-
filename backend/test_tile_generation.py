"""
Test GEE Tile URL Generation for Sentinel-2 RGB, NDWI, Masks, and Change Layers
"""
import ee
from app.services.change_detection import initialize_earth_engine, get_district_aoi, apply_cloud_shadow_mask

def test_tiles():
    initialize_earth_engine()
    aoi = get_district_aoi("Madurai")
    
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate("2023-06-01", "2023-08-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )
    
    if col.size().getInfo() == 0:
        print("No images found!")
        return

    best_img = ee.Image(col.first())
    
    # 1. RGB Map ID
    rgb_vis = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}
    rgb_tile = best_img.select(["B4", "B3", "B2"]).getMapId(rgb_vis)["tile_fetcher"].url_format
    print(f"RGB Tile URL: {rgb_tile}")
    
    # 2. NDWI Map ID
    ndwi = best_img.normalizedDifference(["B3", "B8"]).rename("NDWI")
    ndwi_vis = {"min": -0.2, "max": 0.6, "palette": ["000000", "8B4513", "FFFF00", "00FFFF", "0000FF"]}
    ndwi_tile = ndwi.getMapId(ndwi_vis)["tile_fetcher"].url_format
    print(f"NDWI Tile URL: {ndwi_tile}")
    
    # 3. Water Mask Map ID
    masked = apply_cloud_shadow_mask(best_img)
    water_mask = masked.select("valid_mask").And(ndwi.gte(0.30))
    mask_tile = water_mask.selfMask().getMapId({"palette": ["1D4ED8"]})["tile_fetcher"].url_format
    print(f"Water Mask Tile URL: {mask_tile}")
    
    print("Tile generation test succeeded!")

if __name__ == "__main__":
    test_tiles()
