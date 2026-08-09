import json
import time
from pathlib import Path

import requests


# =========================================================
# SETTINGS
# =========================================================

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = (
    "AquaDetect/1.0 "
    "(water-body mapping project)"
)

MAX_RETRIES = 3
RETRY_DELAY = 10


# =========================================================
# MADURAI AREA
# =========================================================

MADURAI_BBOX = {
    "west": 78.0265,
    "south": 9.8377,
    "east": 78.2196,
    "north": 10.0245,
}


# =========================================================
# OVERPASS QUERY
# =========================================================

def build_query():

    west = MADURAI_BBOX["west"]
    south = MADURAI_BBOX["south"]
    east = MADURAI_BBOX["east"]
    north = MADURAI_BBOX["north"]

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
# REQUEST
# =========================================================

def fetch_osm_data():

    query = build_query()

    for server in OVERPASS_SERVERS:

        print()
        print("======================================")
        print("Trying Overpass server")
        print(server)
        print("======================================")

        for attempt in range(
            1,
            MAX_RETRIES + 1,
        ):

            print(
                f"Attempt {attempt}/{MAX_RETRIES}"
            )

            try:

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

                print(
                    "HTTP status:",
                    response.status_code,
                )

                if response.status_code == 429:

                    print(
                        "Rate limited. Waiting..."
                    )

                    time.sleep(
                        RETRY_DELAY
                    )

                    continue

                if response.status_code >= 500:

                    print(
                        "Server error. Waiting..."
                    )

                    time.sleep(
                        RETRY_DELAY
                    )

                    continue

                response.raise_for_status()

                data = response.json()

                elements = data.get(
                    "elements",
                    [],
                )

                print()
                print(
                    "OSM elements received:",
                    len(elements),
                )

                return data

            except requests.RequestException as error:

                print(
                    "Request failed:"
                )

                print(error)

                if attempt < MAX_RETRIES:

                    time.sleep(
                        RETRY_DELAY
                    )

        print()
        print(
            "Trying next Overpass server..."
        )

    raise RuntimeError(
        "Unable to retrieve OSM data "
        "from the available Overpass servers."
    )


# =========================================================
# SAVE CACHE
# =========================================================

def save_cache(
    data,
    output_file,
):

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
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "OSM cache saved:"
    )

    print(
        output_file
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

    output_file = (
        backend_dir
        / "outputs"
        / "madurai"
        / "madurai_osm_water.json"
    )

    print()
    print(
        "======================================"
    )
    print(
        "MADURAI OSM CACHE"
    )
    print(
        "======================================"
    )

    data = fetch_osm_data()

    save_cache(
        data,
        output_file,
    )

    print()
    print(
        "======================================"
    )
    print(
        "CACHE COMPLETE"
    )
    print(
        "======================================"
    )