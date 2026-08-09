import json
import urllib.request
from pathlib import Path


# ArcGIS Tamil Nadu district boundary service
url = (
    "https://services-ap1.arcgis.com/"
    "Q6vQfsr0oYrwKWlE/"
    "ArcGIS/rest/services/"
    "Tamil_Nadu_District_Boundary/"
    "FeatureServer/0/query"
)


params = (
    "?where=1%3D1"
    "&outFields=*"
    "&returnGeometry=true"
    "&f=geojson"
)


full_url = url + params

print("Downloading Tamil Nadu district boundaries...")

with urllib.request.urlopen(full_url) as response:
    data = json.loads(response.read().decode("utf-8"))


print("Download successful.")

print(
    "Number of district features:",
    len(data.get("features", []))
)


output_path = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "public"
    / "data"
    / "tamil_nadu_districts.geojson"
)


output_path.parent.mkdir(parents=True, exist_ok=True)


with open(output_path, "w", encoding="utf-8") as file:
    json.dump(data, file, ensure_ascii=False)


print()
print("GeoJSON saved to:")
print(output_path)