import sys
import json
from pathlib import Path

import ee
import requests


# =========================================================
# CONFIGURATION
# =========================================================

# Replace this with your actual Google Earth Engine
# Cloud Project ID.
PROJECT_ID = "aquadetect-504614"

# Analysis radius around the supplied district center.
RADIUS_METERS = 10000

# Sentinel-2 date range.
START_DATE = "2026-01-01"
END_DATE = "2026-12-31"

# Maximum cloud percentage.
MAX_CLOUD_PERCENTAGE = 20

# NDWI threshold.
NDWI_THRESHOLD = 0

# Minimum connected Sentinel-2 pixels to keep.
# 20 pixels ~= 2,000 m² at 10 m resolution.
MIN_CONNECTED_PIXELS = 20


# =========================================================
# COMMAND-LINE ARGUMENTS
# =========================================================

if len(sys.argv) != 4:

    print()
    print("Usage:")
    print(
        "python generate_district.py "
        "<district> <latitude> <longitude>"
    )

    print()
    print("Example:")
    print(
        "python generate_district.py "
        "Madurai 9.9252 78.1198"
    )

    print()
    sys.exit(1)


DISTRICT_NAME = sys.argv[1].lower()

try:
    LATITUDE = float(sys.argv[2])
    LONGITUDE = float(sys.argv[3])

except ValueError:

    print(
        "Latitude and longitude must be numbers."
    )

    sys.exit(1)


# =========================================================
# OUTPUT DIRECTORY
# =========================================================

OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "outputs"
    / DISTRICT_NAME
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# START
# =========================================================

print()
print("======================================")
print("AquaDetect District Processing")
print("======================================")

print(
    "District:",
    DISTRICT_NAME
)

print(
    "Latitude:",
    LATITUDE
)

print(
    "Longitude:",
    LONGITUDE
)

print()


# =========================================================
# EARTH ENGINE INITIALIZATION
# =========================================================

print(
    "Connecting to Earth Engine..."
)

try:

    ee.Initialize(
        project=PROJECT_ID
    )

except Exception as error:

    print()
    print(
        "Earth Engine initialization failed."
    )

    print(error)

    print()
    print(
        "Check PROJECT_ID in generate_district.py."
    )

    sys.exit(1)


print(
    "Earth Engine connected."
)

print()


# =========================================================
# CREATE ANALYSIS REGION
# =========================================================

point = ee.Geometry.Point(
    [
        LONGITUDE,
        LATITUDE
    ]
)

region = point.buffer(
    RADIUS_METERS
)


# =========================================================
# FIND SENTINEL-2 IMAGE
# =========================================================

print(
    "Searching for Sentinel-2 images..."
)

collection = (
    ee.ImageCollection(
        "COPERNICUS/S2_SR_HARMONIZED"
    )
    .filterBounds(region)
    .filterDate(
        START_DATE,
        END_DATE
    )
    .filter(
        ee.Filter.lt(
            "CLOUDY_PIXEL_PERCENTAGE",
            MAX_CLOUD_PERCENTAGE
        )
    )
    .sort(
        "CLOUDY_PIXEL_PERCENTAGE"
    )
)


image_count = collection.size().getInfo()

print(
    "Number of Sentinel-2 images:",
    image_count
)


if image_count == 0:

    print()
    print(
        "No suitable Sentinel-2 image was found."
    )

    sys.exit(1)


# =========================================================
# SELECT BEST IMAGE
# =========================================================

image = ee.Image(
    collection.first()
)


image_id = image.get(
    "system:index"
).getInfo()


cloud_percentage = image.get(
    "CLOUDY_PIXEL_PERCENTAGE"
).getInfo()


print()
print(
    "Best Sentinel-2 image:"
)

print(
    image_id
)

print(
    "Cloud percentage:",
    cloud_percentage
)

print()


# =========================================================
# NDWI CALCULATION
# =========================================================

print(
    "Calculating NDWI..."
)

# Sentinel-2:
#
# B3 = Green
# B8 = Near Infrared
#
# NDWI = (B3 - B8) / (B3 + B8)

ndwi = (
    image
    .normalizedDifference(
        [
            "B3",
            "B8"
        ]
    )
    .rename(
        "NDWI"
    )
)


# =========================================================
# WATER MASK
# =========================================================

print(
    "Creating water mask..."
)

water_mask = (
    ndwi
    .gt(NDWI_THRESHOLD)
    .selfMask()
)


# =========================================================
# REMOVE SMALL NOISE
# =========================================================

print(
    "Removing small isolated regions..."
)

connected_pixels = (
    water_mask
    .connectedPixelCount(
        maxSize=100,
        eightConnected=True
    )
)


water_mask = (
    water_mask
    .updateMask(
        connected_pixels.gte(
            MIN_CONNECTED_PIXELS
        )
    )
)


# =========================================================
# WATER PERCENTAGE
# =========================================================

print(
    "Calculating water percentage..."
)

water_area = (
    water_mask
    .multiply(
        ee.Image.pixelArea()
    )
    .reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=10,
        maxPixels=1e9
    )
    .get("NDWI")
)


total_area = region.area()


water_percentage = (
    ee.Number(water_area)
    .divide(
        total_area
    )
    .multiply(100)
)


water_percentage_value = (
    water_percentage
    .getInfo()
)


print(
    "Estimated water percentage:",
    round(
        water_percentage_value,
        2
    ),
    "%"
)


# =========================================================
# EXPORT TIFF
# =========================================================

print()
print(
    "Preparing TIFF download..."
)


tiff_url = water_mask.getDownloadURL(
    {
        "name": (
            f"{DISTRICT_NAME}_water_mask"
        ),

        "region": region,

        "scale": 10,

        "crs": "EPSG:4326",

        "format": "GEO_TIFF"
    }
)


tiff_path = (
    OUTPUT_DIR
    / "water_mask.tif"
)


response = requests.get(
    tiff_url,
    timeout=300
)


response.raise_for_status()


with open(
    tiff_path,
    "wb"
) as file:

    file.write(
        response.content
    )


print(
    "TIFF saved:",
    tiff_path
)


# =========================================================
# CREATE WATER POLYGONS
# =========================================================

print()
print(
    "Creating water polygons..."
)


vectors = (
    water_mask
    .reduceToVectors(
        geometry=region,

        scale=10,

        geometryType="polygon",

        eightConnected=True,

        labelProperty="water",

        maxPixels=1e9
    )
)


# =========================================================
# CONVERT TO GEOJSON
# =========================================================

print(
    "Converting polygons to GeoJSON..."
)


geojson = vectors.getInfo()


geojson_path = (
    OUTPUT_DIR
    / "water_polygons.geojson"
)


with open(
    geojson_path,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        geojson,
        file,
        ensure_ascii=False
    )


print(
    "GeoJSON saved:",
    geojson_path
)


# =========================================================
# FINAL SUMMARY
# =========================================================

polygon_count = len(
    geojson.get(
        "features",
        []
    )
)


print()
print(
    "======================================"
)

print(
    "DISTRICT PROCESSING COMPLETE"
)

print(
    "======================================"
)

print(
    "District:",
    DISTRICT_NAME
)

print(
    "Latitude:",
    LATITUDE
)

print(
    "Longitude:",
    LONGITUDE
)

print(
    "Sentinel-2:",
    image_id
)

print(
    "Cloud:",
    cloud_percentage,
    "%"
)

print(
    "Water:",
    round(
        water_percentage_value,
        2
    ),
    "%"
)

print(
    "Polygons:",
    polygon_count
)

print()

print(
    "Files generated in:"
)

print(
    OUTPUT_DIR
)

print()

print(
    "Generated files:"
)

print(
    " - water_mask.tif"
)

print(
    " - water_polygons.geojson"
)

print()