import math
import requests


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def calculate_distance_km(
    lat1,
    lon1,
    lat2,
    lon2,
):
    """
    Calculate distance between two coordinates
    using the Haversine formula.
    """

    earth_radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(
        lat2 - lat1
    )

    delta_lon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_lat / 2) ** 2
        +
        math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_km * c


def find_nearby_water_body(
    latitude: float,
    longitude: float,
    radius_meters: int = 750,
):
    """
    Find a nearby named water body in OpenStreetMap.

    Returns the closest suitable named feature.
    """

    query = f"""
    [out:json][timeout:20];

    (
      nwr
        ["name"]
        ["natural"="water"]
        (around:{radius_meters},{latitude},{longitude});

      nwr
        ["name"]
        ["landuse"="reservoir"]
        (around:{radius_meters},{latitude},{longitude});

      nwr
        ["name"]
        ["water"="pond"]
        (around:{radius_meters},{latitude},{longitude});

      nwr
        ["name"]
        ["water"="lake"]
        (around:{radius_meters},{latitude},{longitude});

      nwr
        ["name"]
        ["water"="reservoir"]
        (around:{radius_meters},{latitude},{longitude});
    );

    out center tags;
    """

    try:

        response = requests.post(
            OVERPASS_URL,
            data=query,
            timeout=30,
            headers={
                "User-Agent":
                    "AquaDetect/1.0"
            },
        )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as error:

        raise RuntimeError(
            f"OpenStreetMap lookup failed: {error}"
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

        # -----------------------------------------------
        # Get coordinates
        # -----------------------------------------------

        if element.get("type") == "node":

            element_lat = element.get(
                "lat"
            )

            element_lon = element.get(
                "lon"
            )

        else:

            center = element.get(
                "center",
                {},
            )

            element_lat = center.get(
                "lat"
            )

            element_lon = center.get(
                "lon"
            )

        if (
            element_lat is None
            or element_lon is None
        ):
            continue

        # -----------------------------------------------
        # Calculate distance
        # -----------------------------------------------

        distance_km = calculate_distance_km(
            latitude,
            longitude,
            element_lat,
            element_lon,
        )

        candidates.append(
            {
                "name": name,
                "osm_type":
                    element.get("type"),
                "osm_id":
                    element.get("id"),
                "latitude":
                    element_lat,
                "longitude":
                    element_lon,
                "distance_km":
                    round(
                        distance_km,
                        3,
                    ),
                "tags": tags,
            }
        )

    # -----------------------------------------------
    # No named water body found
    # -----------------------------------------------

    if not candidates:

        return {
            "found": False,
            "name": None,
            "message":
                "No named water body found nearby.",
        }

    # -----------------------------------------------
    # Closest candidate
    # -----------------------------------------------

    candidates.sort(
        key=lambda item:
            item["distance_km"]
    )

    best_match = candidates[0]

    return {
        "found": True,
        "name":
            best_match["name"],
        "osm_type":
            best_match["osm_type"],
        "osm_id":
            best_match["osm_id"],
        "latitude":
            best_match["latitude"],
        "longitude":
            best_match["longitude"],
        "distance_km":
            best_match["distance_km"],
        "tags":
            best_match["tags"],
    }