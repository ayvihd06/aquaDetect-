import ee

PROJECT_ID = "aquadetect-504614"

ee.Initialize(project=PROJECT_ID)

print("Earth Engine connected!")

districts = ee.FeatureCollection("FAO/GAUL/2015/level2")

tamil_nadu = (
    districts
    .filter(ee.Filter.eq("ADM0_NAME", "India"))
    .filter(ee.Filter.eq("ADM1_NAME", "Tamil Nadu"))
)

print("Tamil Nadu features:", tamil_nadu.size().getInfo())

names = tamil_nadu.aggregate_array("ADM2_NAME").getInfo()

print("\nTamil Nadu administrative regions:")
for name in sorted(names):
    print("-", name)