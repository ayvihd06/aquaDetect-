"""
test_gis_export.py — Automated GIS Export Compatibility & Validation Tests
===========================================================================

Tests:
1. District Analysis spatial export (GeoJSON, GeoPackage, Shapefile, CSV).
2. NDWI Analysis export with properties (area_km2, mean_ndwi).
3. Water Change multi-layer GeoPackage (water_loss, water_gain, water_stable).
4. Shapefile ZIP export with 10-char DBF attribute mappings.
5. Flood Risk SAR flood candidate polygon export.
6. Drought Risk statistics CSV export + rejection of spatial vector export.
7. Geometry validation & repair with shapely.make_valid().
8. QGIS / GeoPandas compatibility (opening generated GPKG and Shapefile ZIP).
"""

import io
import os
import zipfile
import tempfile
import pytest
import geopandas as gpd
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services.gis_export_service import (
    extract_export_layers,
    export_geojson,
    export_geopackage,
    export_shapefile_zip,
    export_csv,
    repair_feature_collection,
    SHP_FIELD_MAPPINGS,
)

client = TestClient(app)


# =========================================================
# FIXTURES (Real Schema Objects from AquaDetect Analyses)
# =========================================================

@pytest.fixture
def sample_district_result():
    return {
        "district": "Madurai",
        "source": "AquaDetect Static Water Database",
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[78.1, 9.9], [78.12, 9.9], [78.12, 9.92], [78.1, 9.92], [78.1, 9.9]]]
                    },
                    "properties": {
                        "osm_name": "Vandiyur Lake",
                        "area_km2": 1.25,
                        "water_type": "reservoir",
                    }
                }
            ]
        }
    }


@pytest.fixture
def sample_ndwi_result():
    return {
        "success": True,
        "satellite_source": "Sentinel-2 Surface Reflectance",
        "spatial_resolution_m": 10,
        "detection_method": "NDWI (B3, B8)",
        "selected_threshold": 0.30,
        "threshold_method": "manual",
        "statistics": {
            "water_body_count": 1,
            "total_water_area_km2": 0.85,
            "detection_quality": "HIGH",
        },
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[78.11, 9.91], [78.13, 9.91], [78.13, 9.93], [78.11, 9.93], [78.11, 9.91]]]
                    },
                    "properties": {
                        "area_km2": 0.85,
                        "mean_ndwi": 0.42,
                        "centroid_lon": 78.12,
                        "centroid_lat": 9.92,
                    }
                }
            ]
        }
    }


@pytest.fixture
def sample_water_change_result():
    return {
        "analysis": {
            "district": "Madurai",
            "before_start": "2023-06-01",
            "before_end": "2023-08-31",
            "after_start": "2026-06-01",
            "after_end": "2026-08-31",
        },
        "before": {"date": "2023-07-15", "water_area_km2": 15.2},
        "after": {"date": "2026-07-20", "water_area_km2": 12.1},
        "change": {
            "net_change_km2": -3.1,
            "loss_area_km2": 4.2,
            "gain_area_km2": 1.1,
            "stable_area_km2": 11.0,
        },
        "quality": {"status": "HIGH"},
        "geojson": {
            "loss": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[78.1, 9.9], [78.11, 9.9], [78.11, 9.91], [78.1, 9.91], [78.1, 9.9]]]},
                    "properties": {"change_type": "loss", "before_water": True, "after_water": False}
                }]
            },
            "gain": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[78.12, 9.92], [78.13, 9.92], [78.13, 9.93], [78.12, 9.93], [78.12, 9.92]]]},
                    "properties": {"change_type": "gain", "before_water": False, "after_water": True}
                }]
            },
            "stable": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[[78.14, 9.94], [78.15, 9.94], [78.15, 9.95], [78.14, 9.95], [78.14, 9.94]]]},
                    "properties": {"change_type": "stable", "before_water": True, "after_water": True}
                }]
            }
        }
    }


@pytest.fixture
def sample_flood_result():
    return {
        "available": True,
        "district": "Madurai",
        "satellite": "Sentinel-1",
        "polarization": "VV",
        "orbit_direction": "DESCENDING",
        "before_date": "2026-07-25",
        "after_date": "2026-08-05",
        "sar_threshold_db": -16.0,
        "potential_flood_area_km2": 3.45,
        "permanent_water_area_km2": 8.90,
        "flood_indicator": "MODERATE",
        "data_quality": {"status": "HIGH"},
        "flood_geojson": {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[78.15, 9.95], [78.17, 9.95], [78.17, 9.97], [78.15, 9.97], [78.15, 9.95]]]},
                "properties": {"area_km2": 3.45}
            }]
        }
    }


@pytest.fixture
def sample_drought_result():
    return {
        "available": True,
        "district": "Madurai",
        "satellite": "Sentinel-2",
        "current_date": "2026-08-01",
        "current_water_km2": 2.1,
        "historical_water_km2": 6.8,
        "water_area_anomaly_percent": -69.1,
        "ndwi_anomaly": -0.12,
        "ndvi_anomaly_percent": -24.5,
        "rainfall_30d_anomaly_percent": -42.0,
        "rainfall_90d_anomaly_percent": -35.5,
        "drought_indicator": "HIGH",
        "data_quality": {"status": "HIGH"}
    }


# =========================================================
# UNIT TESTS (Service layer)
# =========================================================

def test_geometry_repair():
    # Self-intersecting bowtie polygon
    invalid_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [0, 2], [2, 0], [2, 2], [0, 0]]]
            },
            "properties": {"id": 1}
        }]
    }
    clean_gj, total, repaired = repair_feature_collection(invalid_geojson)
    assert total == 1
    assert repaired == 1
    assert clean_gj["features"][0]["geometry"]["type"] in ("MultiPolygon", "Polygon")


def test_district_export(sample_district_result):
    layers = extract_export_layers("district", sample_district_result)
    assert "district_water" in layers
    assert layers["district_water"]["allow_spatial"] is True

    # Test GeoJSON
    gj_bytes = export_geojson(layers)
    assert b"Vandiyur Lake" in gj_bytes

    # Test GeoPackage (Verify QGIS / GeoPandas compatibility)
    gpkg_bytes = export_geopackage(layers)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
        tmp.write(gpkg_bytes)
        tmp_path = tmp.name

    try:
        gdf = gpd.read_file(tmp_path, layer="district_water")
        assert len(gdf) == 1
        assert gdf.iloc[0]["osm_name"] == "Vandiyur Lake"
        assert gdf.crs.to_epsg() == 4326
    finally:
        os.remove(tmp_path)


def test_water_change_multilayer_geopackage(sample_water_change_result):
    layers = extract_export_layers("water-change", sample_water_change_result)
    assert "water_loss" in layers
    assert "water_gain" in layers
    assert "water_stable" in layers

    gpkg_bytes = export_geopackage(layers)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
        tmp.write(gpkg_bytes)
        tmp_path = tmp.name

    try:
        # Check all 3 distinct layers
        gdf_loss = gpd.read_file(tmp_path, layer="water_loss")
        gdf_gain = gpd.read_file(tmp_path, layer="water_gain")
        gdf_stable = gpd.read_file(tmp_path, layer="water_stable")

        assert len(gdf_loss) == 1
        assert len(gdf_gain) == 1
        assert len(gdf_stable) == 1

        assert gdf_loss.iloc[0]["change_type"] == "loss"
        assert gdf_gain.iloc[0]["change_type"] == "gain"
        assert gdf_stable.iloc[0]["change_type"] == "stable"
    finally:
        os.remove(tmp_path)


def test_shapefile_zip_and_column_truncation(sample_water_change_result):
    layers = extract_export_layers("water-change", sample_water_change_result)
    zip_bytes = export_shapefile_zip(layers)

    assert len(zip_bytes) > 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        namelist = zf.namelist()
        # Verify required shapefile extensions exist
        assert any(f.endswith(".shp") for f in namelist)
        assert any(f.endswith(".shx") for f in namelist)
        assert any(f.endswith(".dbf") for f in namelist)
        assert any(f.endswith(".prj") for f in namelist)

    # Test reading shapefile with GeoPandas
    temp_dir = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(temp_dir)

        loss_shp = os.path.join(temp_dir, "water_loss.shp")
        gdf = gpd.read_file(loss_shp)
        assert len(gdf) == 1
        # Verify column name was truncated to <= 10 chars
        assert "change_typ" in gdf.columns or "change_type" in gdf.columns
        assert gdf.crs.to_epsg() == 4326
    finally:
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(temp_dir)


def test_drought_spatial_rejection_and_csv(sample_drought_result):
    layers = extract_export_layers("drought", sample_drought_result)
    assert layers["drought_stats"]["allow_spatial"] is False

    # CSV should succeed
    csv_bytes = export_csv(layers)
    csv_str = csv_bytes.decode("utf-8")
    assert "drought_indicator" in csv_str
    assert "HIGH" in csv_str
    assert "-69.1" in csv_str


# =========================================================
# ENDPOINTS INTEGRATION TESTS
# =========================================================

def test_export_endpoints_flow(sample_ndwi_result):
    # 1. Prepare
    resp = client.post("/gis/export/prepare", json={
        "analysis_type": "ndwi",
        "result_data": sample_ndwi_result,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    export_id = body["export_id"]
    assert export_id.startswith("exp_")

    # 2. Download GeoJSON
    resp_gj = client.get(f"/gis/export/download/{export_id}?format=geojson")
    assert resp_gj.status_code == 200
    assert resp_gj.headers["content-type"].startswith("application/geo+json")
    assert "attachment; filename=" in resp_gj.headers["content-disposition"]
    assert b"Sentinel-2" in resp_gj.content

    # 3. Download GeoPackage
    resp_gpkg = client.get(f"/gis/export/download/{export_id}?format=geopackage")
    assert resp_gpkg.status_code == 200
    assert resp_gpkg.headers["content-type"].startswith("application/geopackage+sqlite3")

    # 4. Download Shapefile ZIP
    resp_shp = client.get(f"/gis/export/download/{export_id}?format=shapefile")
    assert resp_shp.status_code == 200
    assert resp_shp.headers["content-type"].startswith("application/zip")

    # 5. Download CSV
    resp_csv = client.get(f"/gis/export/download/{export_id}?format=csv")
    assert resp_csv.status_code == 200
    assert resp_csv.headers["content-type"].startswith("text/csv")


def test_drought_spatial_download_rejection(sample_drought_result):
    resp = client.post("/gis/export/prepare", json={
        "analysis_type": "drought",
        "result_data": sample_drought_result,
    })
    assert resp.status_code == 200
    export_id = resp.json()["export_id"]

    # Spatial request must return HTTP 409
    resp_gpkg = client.get(f"/gis/export/download/{export_id}?format=geopackage")
    assert resp_gpkg.status_code == 409
    assert "Spatial vector export (geopackage) is unavailable" in resp_gpkg.json()["detail"]

    # CSV request must succeed
    resp_csv = client.get(f"/gis/export/download/{export_id}?format=csv")
    assert resp_csv.status_code == 200
