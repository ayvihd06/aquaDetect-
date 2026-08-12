import json
import math
from pathlib import Path

from shapely.geometry import shape


# =========================================================
# MATCHING SETTINGS
# =========================================================

# Maximum distance at which an OSM feature can be
# considered for a detected polygon.
MAX_DISTANCE_METERS = 3000


# Minimum confidence required before assigning
# an OSM name.
MIN_CONFIDENCE = 0.50


# =========================================================
# HAVERSINE
# =========================================================

def haversine_distance_m(
    lat1,
    lon1,
    lat2,
    lon2,
):
    earth_radius = 6371000

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    delta_lat = lat2 - lat1
    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius * c


# =========================================================
# OSM GEOMETRY
# =========================================================

def osm_element_to_geometry(
    element,
):
    """
    Convert an OSM way geometry into
    a Shapely geometry.
    """

    geometry = element.get(
        "geometry"
    )

    if not geometry:
        return None

    coordinates = []

    for point in geometry:

        lon = point.get("lon")
        lat = point.get("lat")

        if (
            lon is None
            or lat is None
        ):
            continue

        coordinates.append(
            (
                lon,
                lat,
            )
        )

    if len(coordinates) < 3:
        return None

    # Make sure the polygon is closed.

    if coordinates[0] != coordinates[-1]:

        coordinates.append(
            coordinates[0]
        )

    try:

        polygon = shape(
            {
                "type": "Polygon",
                "coordinates": [
                    coordinates
                ],
            }
        )

        if polygon.is_valid:

            return polygon

        repaired = polygon.buffer(
            0
        )

        if not repaired.is_empty:

            return repaired

    except Exception:

        return None

    return None


# =========================================================
# LOAD OSM CACHE
# =========================================================

def load_osm_candidates(
    osm_file,
):
    """
    Read cached OSM data and convert it
    into spatial candidates.
    """

    print()
    print(
        "Loading OSM cache:"
    )

    print(
        osm_file
    )

    with open(
        osm_file,
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(
            file
        )

    elements = data.get(
        "elements",
        [],
    )

    candidates = []

    for element in elements:

        tags = element.get(
            "tags",
            {},
        )

        name = tags.get(
            "name"
        )

        if not name:
            continue

        geometry = (
            osm_element_to_geometry(
                element
            )
        )

        if geometry is None:
            continue

        centroid = geometry.centroid

        candidates.append(
            {
                "name": name,

                "osm_id":
                    element.get(
                        "id"
                    ),

                "osm_type":
                    element.get(
                        "type"
                    ),

                "geometry":
                    geometry,

                "centroid_lat":
                    centroid.y,

                "centroid_lon":
                    centroid.x,
            }
        )

    print(
        "Named OSM candidates:",
        len(candidates),
    )

    return candidates


# =========================================================
# LOAD DETECTED POLYGONS
# =========================================================

def load_geojson(
    input_file,
):

    print()
    print(
        "Loading detected polygons:"
    )

    print(
        input_file
    )

    with open(
        input_file,
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(
            file
        )

    features = data.get(
        "features",
        [],
    )

    print(
        "Detected polygons:",
        len(features),
    )

    return data


# =========================================================
# GEOMETRY DISTANCE
# =========================================================

def geometry_distance_m(
    detected_geometry,
    osm_geometry,
):
    """
    Approximate Shapely degree distance
    as meters.
    """

    distance_degrees = (
        detected_geometry.distance(
            osm_geometry
        )
    )

    latitude = (
        detected_geometry.centroid.y
    )

    meters_per_degree = (
        111320
        * math.cos(
            math.radians(
                latitude
            )
        )
    )

    return (
        distance_degrees
        * meters_per_degree
    )


# =========================================================
# MATCH ONE POLYGON
# =========================================================

def match_polygon(
    feature,
    candidates,
):
    """
    Find the best OSM match for one
    detected water polygon.
    """

    geometry_data = feature.get(
        "geometry"
    )

    if not geometry_data:
        return None

    try:

        detected = shape(
            geometry_data
        )

    except Exception:

        return None

    if detected.is_empty:
        return None

    detected_area = (
        detected.area
    )

    if detected_area <= 0:
        return None

    best_match = None
    best_score = -1

    for candidate in candidates:

        osm_geometry = candidate[
            "geometry"
        ]

        # -------------------------------------------------
        # DISTANCE
        # -------------------------------------------------

        distance_m = (
            geometry_distance_m(
                detected,
                osm_geometry,
            )
        )

        if (
            distance_m
            > MAX_DISTANCE_METERS
        ):
            continue

        # -------------------------------------------------
        # INTERSECTION
        # -------------------------------------------------

        try:

            intersection = (
                detected.intersection(
                    osm_geometry
                )
            )

            intersection_area = (
                intersection.area
            )

        except Exception:

            intersection_area = 0

        overlap_ratio = (
            intersection_area
            / detected_area
        )

        # -------------------------------------------------
        # CENTROID
        # -------------------------------------------------

        centroid_inside = False

        try:

            centroid_inside = (
                osm_geometry.contains(
                    detected.centroid
                )
            )

        except Exception:

            pass

        # -------------------------------------------------
        # SCORE
        # -------------------------------------------------

        score = 0

        # Strong overlap.

        if overlap_ratio >= 0.50:

            score += 100

        elif overlap_ratio >= 0.25:

            score += 75

        elif overlap_ratio >= 0.10:

            score += 50

        elif overlap_ratio > 0:

            score += 25

        # Centroid inside OSM feature.

        if centroid_inside:

            score += 30

        # Distance bonus.

        distance_score = max(
            0,
            30
            * (
                1
                - (
                    distance_m
                    / MAX_DISTANCE_METERS
                )
            ),
        )

        score += distance_score

        # -------------------------------------------------
        # Keep best
        # -------------------------------------------------

        if score > best_score:

            best_score = score

            best_match = {
                "name":
                    candidate["name"],

                "osm_id":
                    candidate["osm_id"],

                "osm_type":
                    candidate["osm_type"],

                "distance_m":
                    round(
                        distance_m,
                        2,
                    ),

                "overlap_ratio":
                    round(
                        overlap_ratio,
                        4,
                    ),

                "centroid_inside":
                    centroid_inside,

                "score":
                    score,
            }

    if best_match is None:

        return None

    # =====================================================
    # CONFIDENCE
    # =====================================================

    overlap = (
        best_match[
            "overlap_ratio"
        ]
    )

    if overlap >= 0.50:

        confidence = 0.95

    elif overlap >= 0.25:

        confidence = 0.85

    elif overlap >= 0.10:

        confidence = 0.70

    elif best_match[
        "centroid_inside"
    ]:

        confidence = 0.65

    else:

        confidence = max(
            0,
            0.60
            * (
                1
                - (
                    best_match[
                        "distance_m"
                    ]
                    / MAX_DISTANCE_METERS
                )
            ),
        )

    best_match[
        "confidence"
    ] = round(
        confidence,
        2,
    )

    # =====================================================
    # CONSERVATIVE MATCH
    # =====================================================

    if (
        confidence
        < MIN_CONFIDENCE
    ):

        return None

    return best_match


# =========================================================
# ENRICH
# =========================================================

def enrich(
    polygon_file,
    osm_file,
    output_file,
):

    # =====================================================
    # LOAD
    # =====================================================

    geojson = load_geojson(
        polygon_file
    )

    candidates = load_osm_candidates(
        osm_file
    )

    features = geojson.get(
        "features",
        [],
    )

    # =====================================================
    # MATCH
    # =====================================================

    matched = 0
    unmatched = 0

    print()
    print(
        "======================================"
    )

    print(
        "LOCAL OSM MATCHING"
    )

    print(
        "======================================"
    )

    for index, feature in enumerate(
        features,
        start=1,
    ):

        print(
            f"[{index}/{len(features)}]"
        )

        result = match_polygon(
            feature,
            candidates,
        )

        if "properties" not in feature:

            feature[
                "properties"
            ] = {}

        properties = feature[
            "properties"
        ]

        # =================================================
        # NO MATCH
        # =================================================

        if result is None:

            properties[
                "osm_name"
            ] = None

            properties[
                "osm_id"
            ] = None

            properties[
                "osm_type"
            ] = None

            properties[
                "osm_source"
            ] = None

            properties[
                "osm_match_distance_m"
            ] = None

            properties[
                "osm_overlap_ratio"
            ] = None

            properties[
                "osm_match_confidence"
            ] = None

            unmatched += 1

            continue

        # =================================================
        # MATCH
        # =================================================

        properties[
            "osm_name"
        ] = result[
            "name"
        ]

        properties[
            "osm_id"
        ] = result[
            "osm_id"
        ]

        properties[
            "osm_type"
        ] = result[
            "osm_type"
        ]

        properties[
            "osm_source"
        ] = "OpenStreetMap"

        properties[
            "osm_match_distance_m"
        ] = result[
            "distance_m"
        ]

        properties[
            "osm_overlap_ratio"
        ] = result[
            "overlap_ratio"
        ]

        properties[
            "osm_match_confidence"
        ] = result[
            "confidence"
        ]

        matched += 1

        print(
            "   →",
            result["name"],
            "| distance:",
            result["distance_m"],
            "m",
            "| overlap:",
            result["overlap_ratio"],
            "| confidence:",
            result["confidence"],
        )

    # =====================================================
    # SAVE
    # =====================================================

    output_file = Path(
        output_file
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            geojson,
            file,
            ensure_ascii=False,
            indent=2,
        )

    # =====================================================
    # SUMMARY
    # =====================================================

    print()
    print(
        "======================================"
    )

    print(
        "LOCAL MATCHING COMPLETE"
    )

    print(
        "======================================"
    )

    print(
        "Total polygons:",
        len(features),
    )

    print(
        "OSM matched:",
        matched,
    )

    print(
        "OSM unmatched:",
        unmatched,
    )

    print()
    print(
        "Output:"
    )

    print(
        output_file
    )

    print(
        "======================================"
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    backend_dir = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    polygon_file = (
        backend_dir
        / "outputs"
        / "madurai"
        / "water_polygons.geojson"
    )

    osm_file = (
        backend_dir
        / "outputs"
        / "madurai"
        / "madurai_osm_water.json"
    )

    output_file = (
        backend_dir
        / "outputs"
        / "madurai"
        / "water_polygons_enriched.geojson"
    )

    enrich(
        polygon_file,
        osm_file,
        output_file,
    )
    