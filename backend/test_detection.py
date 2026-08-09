from app.services.earth_engine import detect_water


result = detect_water(
    latitude=9.9252,
    longitude=78.1198,
)


print()
print("===================================")
print("AquaDetect Water Detection")
print("===================================")

print("Success:", result["success"])

if result["success"]:

    print(
        "Sentinel-2 image:",
        result["image_id"],
    )

    print(
        "Cloud percentage:",
        result["cloud_percentage"],
    )

    print(
        "Estimated water percentage:",
        result["water_percentage"],
        "%",
    )

    print(
        "Number of polygons:",
        len(
            result["geojson"]["features"]
        ),
    )

else:

    print(
        "Message:",
        result["message"],
    )
    