import json
import os

from shapely.geometry import shape
from shapely.ops import transform
import pyproj


# =========================================================
# SETTINGS
# =========================================================

OUTPUTS_FOLDER = "outputs"

METADATA_FOLDER = os.path.join(
    OUTPUTS_FOLDER,
    "metadata",
)

os.makedirs(
    METADATA_FOLDER,
    exist_ok=True,
)


# =========================================================
# PROJECTION
# =========================================================

project = pyproj.Transformer.from_crs(
    "EPSG:4326",
    "EPSG:3857",
    always_xy=True,
).transform


# =========================================================
# FIND DISTRICTS
# =========================================================

districts = []

for name in os.listdir(OUTPUTS_FOLDER):

    district_folder = os.path.join(
        OUTPUTS_FOLDER,
        name,
    )

    if not os.path.isdir(
        district_folder
    ):
        continue

    geojson_path = os.path.join(
        district_folder,
        "water_polygons.geojson",
    )

    if os.path.exists(
        geojson_path
    ):
        districts.append(name)


districts.sort()


print("=" * 60)
print("AQUADETECT METADATA GENERATOR")
print("=" * 60)

print(
    f"Districts found: {len(districts)}"
)

print()


# =========================================================
# PROCESS EACH DISTRICT
# =========================================================

all_metadata = {}


for district in districts:

    print(
        f"Processing: {district}"
    )


    geojson_path = os.path.join(
        OUTPUTS_FOLDER,
        district,
        "water_polygons.geojson",
    )


    # -----------------------------------------------------
    # LOAD GEOJSON
    # -----------------------------------------------------

    with open(
        geojson_path,
        "r",
        encoding="utf-8",
    ) as file:

        geojson = json.load(file)


    features = geojson.get(
        "features",
        []
    )


    # -----------------------------------------------------
    # CALCULATE AREA
    # -----------------------------------------------------

    total_area_m2 = 0

    bounding_boxes = []


    for index, feature in enumerate(
        features
    ):

        geometry = shape(
            feature["geometry"]
        )


        # ---------------------------------------------
        # AREA
        # ---------------------------------------------

        projected_geometry = transform(
            project,
            geometry,
        )


        area_m2 = (
            projected_geometry.area
        )


        total_area_m2 += area_m2


        # ---------------------------------------------
        # BOUNDING BOX
        # ---------------------------------------------

        (
            min_x,
            min_y,
            max_x,
            max_y,
        ) = geometry.bounds


        bounding_boxes.append(
            {
                "id": index + 1,

                "min_longitude": round(
                    min_x,
                    6,
                ),

                "min_latitude": round(
                    min_y,
                    6,
                ),

                "max_longitude": round(
                    max_x,
                    6,
                ),

                "max_latitude": round(
                    max_y,
                    6,
                ),
            }
        )


    # -----------------------------------------------------
    # AREA IN KM²
    # -----------------------------------------------------

    total_area_km2 = (
        total_area_m2 /
        1_000_000
    )


    # -----------------------------------------------------
    # DISTRICT METADATA
    # -----------------------------------------------------

    metadata = {

        "district": district,

        "total_water_area_km2": round(
            total_area_km2,
            2,
        ),

        "water_body_count": len(
            features
        ),

        "bounding_box_count": len(
            bounding_boxes
        ),

        "bounding_boxes": bounding_boxes,

    }


    # -----------------------------------------------------
    # SAVE DISTRICT METADATA
    # -----------------------------------------------------

    metadata_path = os.path.join(
        METADATA_FOLDER,
        f"{district}.json",
    )


    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2,
        )


    # -----------------------------------------------------
    # STORE FOR MASTER FILE
    # -----------------------------------------------------

    all_metadata[district] = metadata


    print(
        f"  Water area: "
        f"{total_area_km2:.2f} km²"
    )

    print(
        f"  Water bodies: "
        f"{len(features)}"
    )

    print(
        f"  Bounding boxes: "
        f"{len(bounding_boxes)}"
    )

    print()


# =========================================================
# SAVE MASTER METADATA
# =========================================================

master_path = os.path.join(
    METADATA_FOLDER,
    "all_districts.json",
)


with open(
    master_path,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        all_metadata,
        file,
        indent=2,
    )


# =========================================================
# COMPLETE
# =========================================================

print("=" * 60)
print("METADATA GENERATION COMPLETE")
print("=" * 60)

print(
    f"Districts processed: "
    f"{len(districts)}"
)

print(
    f"Metadata folder: "
    f"{METADATA_FOLDER}"
)

print(
    f"Master file: "
    f"{master_path}"
)

print("=" * 60)