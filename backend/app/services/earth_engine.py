import ee


# =========================================================
# EARTH ENGINE CONFIGURATION
# =========================================================

PROJECT_ID = "aquadetect-504614"


def initialize_earth_engine():
    """
    Initialize Google Earth Engine.
    """

    try:
        ee.Initialize(
            project=PROJECT_ID
        )

    except Exception as error:

        raise RuntimeError(
            f"Could not initialize Google Earth Engine: {error}"
        )


# =========================================================
# WATER DETECTION
# =========================================================

def detect_water(
    latitude: float,
    longitude: float,
    radius_meters: int = 10000,
):
    """
    Detect water around a selected latitude/longitude.

    Parameters
    ----------
    latitude:
        Latitude of selected location.

    longitude:
        Longitude of selected location.

    radius_meters:
        Analysis radius around selected location.

    Returns
    -------
    dict
        Detection result including water percentage
        and GeoJSON polygons.
    """

    initialize_earth_engine()


    # =====================================================
    # CREATE ANALYSIS REGION
    # =====================================================

    point = ee.Geometry.Point(
        [
            longitude,
            latitude,
        ]
    )

    region = point.buffer(
        radius_meters
    )


    # =====================================================
    # SENTINEL-2 COLLECTION
    # =====================================================

    collection = (
        ee.ImageCollection(
            "COPERNICUS/S2_SR_HARMONIZED"
        )
        .filterBounds(region)
        .filterDate(
            "2026-01-01",
            "2026-12-31",
        )
        .filter(
            ee.Filter.lt(
                "CLOUDY_PIXEL_PERCENTAGE",
                20,
            )
        )
        .sort(
            "CLOUDY_PIXEL_PERCENTAGE"
        )
    )


    # =====================================================
    # CHECK IMAGES
    # =====================================================

    count = (
        collection
        .size()
        .getInfo()
    )


    if count == 0:

        return {
            "success": False,
            "message": (
                "No suitable Sentinel-2 image found."
            ),
        }


    # =====================================================
    # SELECT BEST IMAGE
    # =====================================================

    image = ee.Image(
        collection.first()
    )


    image_id = (
        image
        .get("system:index")
        .getInfo()
    )


    cloud_percentage = (
        image
        .get(
            "CLOUDY_PIXEL_PERCENTAGE"
        )
        .getInfo()
    )


    # =====================================================
    # CALCULATE NDWI
    # =====================================================

    ndwi = (
        image
        .normalizedDifference(
            [
                "B3",
                "B8",
            ]
        )
        .rename("NDWI")
    )


    # =====================================================
    # CREATE WATER MASK
    # =====================================================

    water_mask = (
        ndwi
        .gt(0)
        .selfMask()
    )


    # =====================================================
    # REMOVE SMALL NOISE
    # =====================================================

    connected_pixels = (
        water_mask
        .connectedPixelCount(
            maxSize=100,
            eightConnected=True,
        )
    )


    water_mask = (
        water_mask
        .updateMask(
            connected_pixels.gte(20)
        )
    )


    # =====================================================
    # CALCULATE WATER AREA
    # =====================================================

    water_area = (
        water_mask
        .multiply(
            ee.Image.pixelArea()
        )
        .reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=region,
            scale=10,
            maxPixels=1e9,
        )
        .get("NDWI")
    )


    total_area = (
        region.area()
    )


    water_percentage = (
        ee.Number(
            water_area
        )
        .divide(
            total_area
        )
        .multiply(100)
    )


    water_percentage_value = (
        water_percentage
        .getInfo()
    )


    # =====================================================
    # CREATE WATER POLYGONS
    # =====================================================

    vectors = (
        water_mask
        .reduceToVectors(
            geometry=region,
            scale=10,
            geometryType="polygon",
            eightConnected=True,
            labelProperty="water",
            maxPixels=1e9,
        )
    )


    # =====================================================
    # CONVERT TO GEOJSON
    # =====================================================

    geojson = (
        vectors
        .getInfo()
    )


    # =====================================================
    # POLYGON COUNT
    # =====================================================

    polygon_count = len(
        geojson.get(
            "features",
            []
        )
    )


    # =====================================================
    # RETURN RESULT
    # =====================================================

    return {
        "success": True,

        "latitude": latitude,

        "longitude": longitude,

        "radius_meters": radius_meters,

        "image_id": image_id,

        "cloud_percentage": cloud_percentage,

        "water_percentage": round(
            water_percentage_value,
            2,
        ),

        "polygon_count": polygon_count,

        "geojson": geojson,
    }