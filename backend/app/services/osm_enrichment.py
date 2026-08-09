import json
import math
import time
from pathlib import Path

import requests

from shapely.geometry import (
    shape,
    Polygon,
    MultiPolygon,
    LineString,
)

from shapely.ops import (
    unary_union,
    polygonize,
)


# =========================================================
# CONFIGURATION
# =========================================================

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = (
    "AquaDetect/1.0 "
    "(water-body enrichment project)"
)

GRID_ROWS = 2
GRID_COLUMNS = 2

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

CELL_BUFFER = 0.005


# =========================================================
# HAVERSINE DISTANCE
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
# GEOJSON BOUNDING BOX
# =========================================================

def get_geojson_bbox(geojson):

    bounds = []

    for feature in geojson.get(
        "features",
        [],
    ):

        geometry = feature.get(
            "geometry"
        )

        if not geometry:
            continue

        try:

            polygon = shape(
                geometry
            )

            min_x, min_y, max_x, max_y = (
                polygon.bounds
            )

            bounds.append(
                (
                    min_x,
                    min_y,
                    max_x,
                    max_y,
                )
            )

        except Exception:
            continue

    if not bounds:
        raise RuntimeError(
            "Could not determine GeoJSON bounding box."
        )

    west = min(
        item[0]
        for item in bounds
    )

    south = min(
        item[1]
        for item in bounds
    )

    east = max(
        item[2]
        for item in bounds
    )

    north = max(
        item[3]
        for item in bounds
    )

    return (
        west,
        south,
        east,
        north,
    )


# =========================================================
# CREATE GRID
# =========================================================

def create_grid(
    west,
    south,
    east,
    north,
):

    longitude_step = (
        east - west
    ) / GRID_COLUMNS

    latitude_step = (
        north - south
    ) / GRID_ROWS

    cells = []

    for row in range(
        GRID_ROWS
    ):

        for column in range(
            GRID_COLUMNS
        ):

            cell_west = (
                west
                + column
                * longitude_step
            )

            cell_east = (
                west
                + (column + 1)
                * longitude_step
            )

            cell_south = (
                south
                + row
                * latitude_step
            )

            cell_north = (
                south
                + (row + 1)
                * latitude_step
            )

            cell_west -= CELL_BUFFER
            cell_east += CELL_BUFFER
            cell_south -= CELL_BUFFER
            cell_north += CELL_BUFFER

            cells.append(
                (
                    cell_west,
                    cell_south,
                    cell_east,
                    cell_north,
                )
            )

    return cells


# =========================================================
# OVERPASS QUERY
# =========================================================

def build_overpass_query(
    west,
    south,
    east,
    north,
):

    return f"""
[out:json][timeout:60];

(
  way
    ["name"]
    ["natural"="water"]
    ({south},{west},{north},{east});

  relation
    ["name"]
    ["natural"="water"]
    ({south},{west},{north},{east});

  way
    ["name"]
    ["landuse"="reservoir"]
    ({south},{west},{north},{east});

  relation
    ["name"]
    ["landuse"="reservoir"]
    ({south},{west},{north},{east});

  way
    ["name"]
    ["water"="lake"]
    ({south},{west},{north},{east});

  relation
    ["name"]
    ["water"="lake"]
    ({south},{west},{north},{east});

  way
    ["name"]
    ["water"="pond"]
    ({south},{west},{north},{east});

  relation
    ["name"]
    ["water"="pond"]
    ({south},{west},{north},{east});

  way
    ["name"]
    ["water"="reservoir"]
    ({south},{west},{north},{east});

  relation
    ["name"]
    ["water"="reservoir"]
    ({south},{west},{north},{east});
);

out geom tags;
"""


# =========================================================
# QUERY ONE CELL
# =========================================================

def query_overpass_cell(
    cell,
    cell_number,
    total_cells,
):

    west, south, east, north = cell

    print()
    print("--------------------------------------")

    print(
        f"OSM cell {cell_number}/{total_cells}"
    )

    query = build_overpass_query(
        west,
        south,
        east,
        north,
    )

    for server in OVERPASS_SERVERS:

        print()
        print(
            "Using Overpass server:"
        )
        print(server)

        for attempt in range(
            1,
            MAX_RETRIES + 1,
        ):

            try:

                print(
                    f"Attempt {attempt}/"
                    f"{MAX_RETRIES}"
                )

                response = requests.post(
                    server,
                    data=query,
                    headers={
                        "User-Agent":
                            USER_AGENT,
                        "Content-Type":
                            "application/x-www-form-urlencoded",
                    },
                    timeout=120,
                )

                if response.status_code == 429:

                    print(
                        "Rate limited."
                    )

                    time.sleep(
                        RETRY_DELAY_SECONDS
                    )

                    continue

                if response.status_code >= 500:

                    print(
                        "Overpass server error:",
                        response.status_code,
                    )

                    time.sleep(
                        RETRY_DELAY_SECONDS
                    )

                    continue

                response.raise_for_status()

                data = response.json()

                elements = data.get(
                    "elements",
                    [],
                )

                print(
                    "OSM elements returned:",
                    len(elements),
                )

                return elements

            except requests.RequestException as error:

                print(
                    "Request failed:"
                )

                print(error)

                if attempt < MAX_RETRIES:

                    time.sleep(
                        RETRY_DELAY_SECONDS
                    )

        print(
            "Switching Overpass server..."
        )

    raise RuntimeError(
        "All Overpass servers failed "
        "for this cell."
    )


# =========================================================
# QUERY COMPLETE AREA
# =========================================================

def query_osm_water_features(
    west,
    south,
    east,
    north,
):

    cells = create_grid(
        west,
        south,
        east,
        north,
    )

    print()
    print(
        f"OSM grid cells: {len(cells)}"
    )

    all_elements = []

    for index, cell in enumerate(
        cells,
        start=1,
    ):

        elements = query_overpass_cell(
            cell,
            index,
            len(cells),
        )

        all_elements.extend(
            elements
        )

        if index < len(cells):
            time.sleep(2)

    # =====================================================
    # REMOVE DUPLICATES
    # =====================================================

    unique = {}

    for element in all_elements:

        key = (
            element.get("type"),
            element.get("id"),
        )

        unique[key] = element

    result = list(
        unique.values()
    )

    print()
    print(
        "Unique OSM elements:",
        len(result),
    )

    return result


# =========================================================
# CONVERT OSM WAY TO SHAPELY
# =========================================================

def osm_way_to_geometry(
    element,
):

    geometry = element.get(
        "geometry"
    )

    if not geometry:
        return None

    coordinates = []

    for point in geometry:

        lon = point.get(
            "lon"
        )

        lat = point.get(
            "lat"
        )

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

    # -----------------------------------------------------
    # Closed way → polygon
    # -----------------------------------------------------

    if coordinates[0] != coordinates[-1]:

        coordinates.append(
            coordinates[0]
        )

    try:

        polygon = Polygon(
            coordinates
        )

        if polygon.is_valid:

            return polygon

        # Attempt to repair invalid polygon.

        repaired = polygon.buffer(
            0
        )

        if not repaired.is_empty:

            return repaired

    except Exception:

        return None

    return None


# =========================================================
# CONVERT OSM RELATION TO SHAPELY
# =========================================================

def osm_relation_to_geometry(
    element,
):

    members = element.get(
        "members",
        [],
    )

    lines = []

    for member in members:

        if member.get(
            "type"
        ) != "way":

            continue

        geometry = member.get(
            "geometry"
        )

        if not geometry:
            continue

        coordinates = []

        for point in geometry:

            lon = point.get(
                "lon"
            )

            lat = point.get(
                "lat"
            )

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

        if len(coordinates) < 2:
            continue

        try:

            line = LineString(
                coordinates
            )

            lines.append(
                line
            )

        except Exception:

            continue

    if not lines:
        return None

    try:

        polygons = list(
            polygonize(
                lines
            )
        )

        if not polygons:
            return None

        result = unary_union(
            polygons
        )

        if result.is_empty:
            return None

        return result

    except Exception:

        return None


# =========================================================
# CONVERT OSM ELEMENT
# =========================================================

def osm_element_to_geometry(
    element,
):

    element_type = element.get(
        "type"
    )

    if element_type == "way":

        return osm_way_to_geometry(
            element
        )

    if element_type == "relation":

        return osm_relation_to_geometry(
            element
        )

    return None


# =========================================================
# PREPARE OSM CANDIDATES
# =========================================================

def prepare_osm_candidates(
    elements,
):

    candidates = []

    skipped = 0

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

            skipped += 1

            continue

        if geometry.is_empty:

            continue

        centroid = (
            geometry.centroid
        )

        candidates.append(
            {
                "name":
                    name,

                "osm_type":
                    element.get(
                        "type"
                    ),

                "osm_id":
                    element.get(
                        "id"
                    ),

                "geometry":
                    geometry,

                "centroid_lat":
                    centroid.y,

                "centroid_lon":
                    centroid.x,

                "tags":
                    tags,
            }
        )

    print()
    print(
        "OSM candidates with geometry:",
        len(candidates),
    )

    print(
        "OSM elements skipped:",
        skipped,
    )

    return candidates


# =========================================================
# APPROXIMATE DISTANCE IN METERS
# =========================================================

def geometry_distance_m(
    geometry_a,
    geometry_b,
):

    distance_degrees = (
        geometry_a.distance(
            geometry_b
        )
    )

    center_lat = (
        geometry_a.centroid.y
    )

    meters_per_degree = (
        111320
        * math.cos(
            math.radians(
                center_lat
            )
        )
    )

    return (
        distance_degrees
        * meters_per_degree
    )


# =========================================================
# MATCH POLYGON
# =========================================================

def match_polygon(
    feature,
    candidates,
):

    geometry_data = feature.get(
        "geometry"
    )

    if not geometry_data:
        return None

    try:

        detected_polygon = shape(
            geometry_data
        )

    except Exception:

        return None

    if detected_polygon.is_empty:
        return None

    detected_area = (
        detected_polygon.area
    )

    if detected_area <= 0:
        return None

    # =====================================================
    # SEARCH RADIUS
    # =====================================================

    min_lon, min_lat, max_lon, max_lat = (
        detected_polygon.bounds
    )

    center_lat = (
        detected_polygon.centroid.y
    )

    latitude_size_m = (
        abs(max_lat - min_lat)
        * 111320
    )

    longitude_size_m = (
        abs(max_lon - min_lon)
        * 111320
        * math.cos(
            math.radians(
                center_lat
            )
        )
    )

    polygon_size_m = max(
        latitude_size_m,
        longitude_size_m,
        100,
    )

    search_radius_m = max(
        500,
        polygon_size_m * 2,
    )

    matches = []

    # =====================================================
    # COMPARE WITH OSM
    # =====================================================

    for candidate in candidates:

        osm_geometry = candidate[
            "geometry"
        ]

        # -------------------------------------------------
        # Distance
        # -------------------------------------------------

        distance_m = (
            geometry_distance_m(
                detected_polygon,
                osm_geometry,
            )
        )

        if distance_m > search_radius_m:
            continue

        # -------------------------------------------------
        # Intersection
        # -------------------------------------------------

        try:

            intersection = (
                detected_polygon.intersection(
                    osm_geometry
                )
            )

            intersection_area = (
                intersection.area
            )

        except Exception:

            intersection_area = 0

        # -------------------------------------------------
        # Overlap relative to detected polygon
        # -------------------------------------------------

        overlap_ratio = (
            intersection_area
            / detected_area
        )

        # -------------------------------------------------
        # OSM containment
        # -------------------------------------------------

        osm_contains_detected = False

        try:

            osm_contains_detected = (
                osm_geometry.contains(
                    detected_polygon
                )
            )

        except Exception:

            pass

        # -------------------------------------------------
        # Detected polygon centroid inside OSM
        # -------------------------------------------------

        centroid_inside_osm = False

        try:

            centroid_inside_osm = (
                osm_geometry.contains(
                    detected_polygon.centroid
                )
            )

        except Exception:

            pass

        # =================================================
        # SCORE
        # =================================================

        score = 0

        # Strongest signal:
        # substantial intersection.

        if overlap_ratio >= 0.50:

            score += 100

        elif overlap_ratio >= 0.25:

            score += 75

        elif overlap_ratio >= 0.10:

            score += 50

        elif overlap_ratio > 0:

            score += 25

        # OSM contains detected polygon.

        if osm_contains_detected:

            score += 40

        # Centroid inside OSM.

        if centroid_inside_osm:

            score += 25

        # Distance bonus.

        distance_score = max(
            0,
            30
            * (
                1
                - (
                    distance_m
                    / search_radius_m
                )
            ),
        )

        score += distance_score

        # -------------------------------------------------
        # Save candidate
        # -------------------------------------------------

        matches.append(
            {
                **candidate,

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

                "osm_contains_detected":
                    osm_contains_detected,

                "centroid_inside_osm":
                    centroid_inside_osm,

                "score":
                    score,
            }
        )

    if not matches:
        return None

    # =====================================================
    # BEST MATCH
    # =====================================================

    matches.sort(
        key=lambda item:
            item["score"],
        reverse=True,
    )

    best = matches[0]

    # =====================================================
    # CONFIDENCE
    # =====================================================

    overlap = best[
        "overlap_ratio"
    ]

    if overlap >= 0.50:

        confidence = 0.95

    elif overlap >= 0.25:

        confidence = 0.85

    elif overlap >= 0.10:

        confidence = 0.70

    elif (
        best[
            "osm_contains_detected"
        ]
        or best[
            "centroid_inside_osm"
        ]
    ):

        confidence = 0.65

    else:

        # Distance-only match.

        ratio = (
            best["distance_m"]
            / search_radius_m
        )

        confidence = max(
            0,
            0.60 * (1 - ratio),
        )

    # =====================================================
    # CONSERVATIVE THRESHOLD
    # =====================================================

    # Don't assign a name when there is
    # almost no spatial evidence.

    if (
        confidence < 0.50
        and overlap <= 0
    ):

        return None

    best[
        "match_confidence"
    ] = round(
        confidence,
        2,
    )

    return best


# =========================================================
# ENRICH GEOJSON
# =========================================================

def enrich_geojson(
    input_path,
    output_path,
):

    input_path = Path(
        input_path
    )

    output_path = Path(
        output_path
    )

    # =====================================================
    # LOAD GEOJSON
    # =====================================================

    print()
    print(
        "Loading GeoJSON:"
    )

    print(
        input_path
    )

    with open(
        input_path,
        "r",
        encoding="utf-8",
    ) as file:

        geojson = json.load(
            file
        )

    features = geojson.get(
        "features",
        [],
    )

    print(
        "Detected polygons:",
        len(features),
    )

    if not features:

        raise RuntimeError(
            "GeoJSON contains no features."
        )

    # =====================================================
    # BOUNDING BOX
    # =====================================================

    (
        west,
        south,
        east,
        north,
    ) = get_geojson_bbox(
        geojson
    )

    buffer = 0.01

    west -= buffer
    south -= buffer
    east += buffer
    north += buffer

    print()
    print(
        "District bounding box:"
    )

    print(
        west,
        south,
        east,
        north,
    )

    # =====================================================
    # QUERY OSM
    # =====================================================

    osm_elements = (
        query_osm_water_features(
            west,
            south,
            east,
            north,
        )
    )

    candidates = (
        prepare_osm_candidates(
            osm_elements
        )
    )

    # =====================================================
    # MATCH
    # =====================================================

    matched_count = 0
    unmatched_count = 0

    match_details = []

    for index, feature in enumerate(
        features,
        start=1,
    ):

        print(
            f"[{index}/{len(features)}] "
            "Matching polygon..."
        )

        match = match_polygon(
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
        # UNMATCHED
        # =================================================

        if match is None:

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
                "osm_match_confidence"
            ] = None

            properties[
                "osm_overlap_ratio"
            ] = None

            properties[
                "osm_match_inside_polygon"
            ] = False

            unmatched_count += 1

            continue

        # =================================================
        # MATCHED
        # =================================================

        properties[
            "osm_name"
        ] = match[
            "name"
        ]

        properties[
            "osm_id"
        ] = match[
            "osm_id"
        ]

        properties[
            "osm_type"
        ] = match[
            "osm_type"
        ]

        properties[
            "osm_source"
        ] = "OpenStreetMap"

        properties[
            "osm_match_distance_m"
        ] = match[
            "distance_m"
        ]

        properties[
            "osm_match_confidence"
        ] = match[
            "match_confidence"
        ]

        properties[
            "osm_overlap_ratio"
        ] = match[
            "overlap_ratio"
        ]

        properties[
            "osm_match_inside_polygon"
        ] = (
            match[
                "centroid_inside_osm"
            ]
            or match[
                "osm_contains_detected"
            ]
        )

        matched_count += 1

        match_details.append(
            {
                "polygon":
                    index,

                "name":
                    match[
                        "name"
                    ],

                "distance_m":
                    match[
                        "distance_m"
                    ],

                "overlap":
                    match[
                        "overlap_ratio"
                    ],

                "confidence":
                    match[
                        "match_confidence"
                    ],
            }
        )

        print(
            "    →",
            match["name"],
            "| distance:",
            match["distance_m"],
            "m | overlap:",
            match["overlap_ratio"],
            "| confidence:",
            match[
                "match_confidence"
            ],
        )

    # =====================================================
    # SAVE
    # =====================================================

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
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
        "OSM GEOMETRY ENRICHMENT COMPLETE"
    )

    print(
        "======================================"
    )

    print(
        "Input polygons:",
        len(features),
    )

    print(
        "OSM matched:",
        matched_count,
    )

    print(
        "OSM unmatched:",
        unmatched_count,
    )

    print()
    print(
        "MATCHED WATER BODIES"
    )

    print(
        "--------------------------------------"
    )

    for item in match_details:

        print(
            f"Polygon {item['polygon']}: "
            f"{item['name']} | "
            f"{item['distance_m']} m | "
            f"overlap={item['overlap']} | "
            f"confidence={item['confidence']}"
        )

    print()
    print(
        "Output:"
    )

    print(
        output_path
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

    input_file = (
        backend_dir
        / "outputs"
        / "madurai"
        / "water_polygons.geojson"
    )

    output_file = (
        backend_dir
        / "outputs"
        / "madurai"
        / "water_polygons_enriched.geojson"
    )

    enrich_geojson(
        input_path=input_file,
        output_path=output_file,
    )