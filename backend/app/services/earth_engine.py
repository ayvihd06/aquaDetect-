import ee
import logging

logger = logging.getLogger(__name__)

# =========================================================
# EARTH ENGINE CONFIGURATION
# =========================================================

PROJECT_ID = "aquadetect-504614"


def initialize_earth_engine():
    """
    Initialize Google Earth Engine.
    """
    try:
        ee.Initialize(project=PROJECT_ID)
    except Exception as error:
        raise RuntimeError(f"Could not initialize Google Earth Engine: {error}")


def apply_cloud_shadow_mask(image: ee.Image) -> ee.Image:
    """
    Applies cloud and shadow mask using Scene Classification Layer (SCL).
    SCL: 0=No data, 1=Defective, 2=Dark/Shadows, 3=Cloud shadows, 8,9,10=Clouds/Cirrus
    """
    scl = image.select("SCL")
    invalid_mask = (
        scl.eq(0)
        .Or(scl.eq(1))
        .Or(scl.eq(2))
        .Or(scl.eq(3))
        .Or(scl.eq(8))
        .Or(scl.eq(9))
        .Or(scl.eq(10))
    )
    valid_mask = invalid_mask.Not().rename("valid_mask")
    return image.addBands(valid_mask)


# =========================================================
# WATER DETECTION
# =========================================================

def detect_water(
    latitude: float,
    longitude: float,
    radius_meters: int = 10000,
    threshold: float = 0.30,
):
    """
    Detect water around a selected latitude/longitude with cloud masking and NDWI diagnostics.
    """
    initialize_earth_engine()

    point = ee.Geometry.Point([longitude, latitude])
    region = point.buffer(radius_meters)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate("2026-01-01", "2026-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    count = collection.size().getInfo()

    if count == 0:
        return {
            "success": False,
            "message": "No suitable Sentinel-2 image found.",
        }

    raw_image = ee.Image(collection.first())
    image_id = str(raw_image.get("system:index").getInfo())
    cloud_percentage = float(raw_image.get("CLOUDY_PIXEL_PERCENTAGE").getInfo() or 0.0)

    # Cloud & Shadow Masking
    masked_image = apply_cloud_shadow_mask(raw_image)
    valid_mask = masked_image.select("valid_mask")

    # NDWI = (B3 - B8) / (B3 + B8)
    ndwi = masked_image.normalizedDifference(["B3", "B8"]).rename("NDWI")

    # Compute NDWI Stats over region
    ndwi_stats = ndwi.updateMask(valid_mask).reduceRegion(
        reducer=ee.Reducer.minMax()
        .combine(ee.Reducer.mean(), "", True)
        .combine(ee.Reducer.median(), "", True),
        geometry=region,
        scale=20,
        maxPixels=1e9,
    ).getInfo() or {}

    # Water Mask: NDWI >= threshold AND valid pixel
    water_mask = ndwi.gte(threshold).And(valid_mask).selfMask()

    # Noise filter: connected pixels >= 15
    connected_pixels = water_mask.connectedPixelCount(maxSize=100, eightConnected=True)
    water_mask = water_mask.updateMask(connected_pixels.gte(15))

    # Calculate water area
    water_area_m2 = (
        water_mask.multiply(ee.Image.pixelArea())
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=region,
            scale=10,
            maxPixels=1e9,
        )
        .get("NDWI")
        .getInfo() or 0.0
    )

    total_area_m2 = region.area().getInfo() or 1.0
    water_percentage = (water_area_m2 / total_area_m2) * 100.0

    vectors = water_mask.reduceToVectors(
        geometry=region,
        scale=10,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="water",
        maxPixels=1e9,
    )

    geojson = vectors.getInfo() or {"type": "FeatureCollection", "features": []}
    polygon_count = len(geojson.get("features", []))

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "radius_meters": radius_meters,
        "image_id": f"COPERNICUS/S2_SR_HARMONIZED/{image_id}",
        "cloud_percentage": round(cloud_percentage, 2),
        "water_percentage": round(water_percentage, 2),
        "polygon_count": polygon_count,
        "ndwi_threshold": threshold,
        "ndwi_stats": {
            "ndwi_min": round(float(ndwi_stats.get("NDWI_min") or -1.0), 4),
            "ndwi_max": round(float(ndwi_stats.get("NDWI_max") or 1.0), 4),
            "ndwi_mean": round(float(ndwi_stats.get("NDWI_mean") or 0.0), 4),
            "ndwi_median": round(float(ndwi_stats.get("NDWI_median") or 0.0), 4),
        },
        "metadata": {
            "satellite": "Sentinel-2",
            "green_band": "B3",
            "nir_band": "B8",
        },
        "geojson": geojson,
    }