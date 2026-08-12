"""
gis_export_service.py — Production-Quality GIS Export Service for AquaDetect
=============================================================================

Handles:
1. Validation and repair of GeoJSON features (using shapely.make_valid()).
2. Generation of RFC 7946 compliant GeoJSON files.
3. Multi-layer GeoPackage (.gpkg) file creation using GeoPandas.
4. ESRI Shapefile (.zip) generation with automatic 10-char DBF field truncation.
5. Tabular CSV statistical/attribute export.
6. In-memory TTL caching for export IDs to prevent payload tampering and re-runs.

All exported data is based strictly on real AquaDetect analysis outputs.
"""

import io
import os
import zipfile
import tempfile
import time
import logging
import uuid
from typing import Dict, Any, List, Tuple, Optional

import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, mapping
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 50 * 1024 * 1024  # 50 MB limit
CACHE_TTL_SECONDS = 900  # 15 minutes

# =========================================================
# SHAPEFILE 10-CHARACTER DBF FIELD NAME MAPPINGS
# =========================================================
SHP_FIELD_MAPPINGS = {
    "change_type": "change_typ",
    "before_water": "bfr_water",
    "after_water": "aft_water",
    "before_date": "bfr_date",
    "after_date": "aft_date",
    "centroid_lon": "cntr_lon",
    "centroid_lat": "cntr_lat",
    "mean_ndwi": "mean_ndwi",
    "area_km2": "area_km2",
    "water_type": "water_type",
    "osm_name": "osm_name",
    "potential_flood_area_km2": "fld_area_km",
    "permanent_water_area_km2": "prm_wat_km",
    "sar_threshold_db": "sar_thresh",
    "orbit_direction": "orbit_dir",
    "flood_indicator": "fld_ind",
    "drought_indicator": "drt_ind",
    "water_area_anomaly_percent": "wat_anom_pct",
    "rainfall_30d_anomaly_percent": "rain30_anom",
    "rainfall_90d_anomaly_percent": "rain90_anom",
    "ndvi_anomaly_percent": "ndvi_anom",
}


# =========================================================
# IN-MEMORY EXPORT CACHE
# =========================================================
class ExportCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def store(self, data: Dict[str, Any]) -> str:
        self.cleanup()
        export_id = f"exp_{uuid.uuid4().hex[:12]}"
        self._cache[export_id] = {
            "data": data,
            "created_at": time.time(),
        }
        return export_id

    def get(self, export_id: str) -> Optional[Dict[str, Any]]:
        self.cleanup()
        entry = self._cache.get(export_id)
        if entry:
            return entry["data"]
        return None

    def cleanup(self):
        now = time.time()
        expired = [
            k for k, v in self._cache.items()
            if now - v["created_at"] > CACHE_TTL_SECONDS
        ]
        for k in expired:
            del self._cache[k]


export_cache = ExportCache()


# =========================================================
# GEOMETRY VALIDATION & REPAIR
# =========================================================
def repair_feature_collection(geojson: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
    """
    Parses and validates GeoJSON features. Repairs invalid geometries with shapely.make_valid().
    Returns: (cleaned_geojson, total_features, repaired_count)
    """
    if not isinstance(geojson, dict):
        return {"type": "FeatureCollection", "features": []}, 0, 0

    features = geojson.get("features", [])
    cleaned_features = []
    repaired_count = 0

    for feat in features:
        if not isinstance(feat, dict) or "geometry" not in feat or not feat["geometry"]:
            continue

        try:
            geom_obj = shape(feat["geometry"])
            if geom_obj.is_empty:
                continue

            if not geom_obj.is_valid:
                repaired = make_valid(geom_obj)
                if not repaired.is_empty:
                    feat["geometry"] = mapping(repaired)
                    repaired_count += 1
                else:
                    continue

            cleaned_features.append(feat)

        except Exception as err:
            logger.warning("Skipping unparseable geometry: %s", err)
            continue

    cleaned_geojson = {
        "type": "FeatureCollection",
        "features": cleaned_features,
    }
    return cleaned_geojson, len(cleaned_features), repaired_count


# =========================================================
# ANALYSIS ADAPTERS (Extracting Layers from Result Payload)
# =========================================================
def extract_export_layers(analysis_type: str, result_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extracts spatial layer dictionaries from analysis outputs.
    Returns dict of layer_name -> { "geojson": FeatureCollection, "metadata": dict, "allow_spatial": bool }
    """
    layers = {}

    if analysis_type == "district":
        geojson = result_data.get("geojson") or {"type": "FeatureCollection", "features": []}
        clean_gj, total, repaired = repair_feature_collection(geojson)
        district_name = result_data.get("district", "District")
        layers["district_water"] = {
            "geojson": clean_gj,
            "metadata": {
                "district": district_name,
                "source": result_data.get("source", "AquaDetect Static Water Database"),
                "analysis_type": "district",
                "feature_count": total,
                "repaired_geometries": repaired,
            },
            "allow_spatial": True,
        }

    elif analysis_type in ("ndwi", "image"):
        geojson = result_data.get("geojson") or {"type": "FeatureCollection", "features": []}
        clean_gj, total, repaired = repair_feature_collection(geojson)
        stats = result_data.get("statistics") or {}
        layers["ndwi_water"] = {
            "geojson": clean_gj,
            "metadata": {
                "satellite_source": result_data.get("satellite_source", "Sentinel-2 Surface Reflectance"),
                "spatial_resolution_m": result_data.get("spatial_resolution_m", 10),
                "detection_method": result_data.get("detection_method", "NDWI (B3, B8)"),
                "selected_threshold": result_data.get("selected_threshold"),
                "threshold_method": result_data.get("threshold_method"),
                "total_water_area_km2": stats.get("total_water_area_km2"),
                "water_body_count": stats.get("water_body_count", total),
                "detection_quality": stats.get("detection_quality", "UNKNOWN"),
                "analysis_type": "ndwi",
                "feature_count": total,
                "repaired_geometries": repaired,
            },
            "allow_spatial": True,
        }

    elif analysis_type in ("water-change", "change"):
        gj_data = result_data.get("geojson") or {}
        analysis_meta = result_data.get("analysis") or {}
        before_meta = result_data.get("before") or {}
        after_meta = result_data.get("after") or {}
        change_meta = result_data.get("change") or {}
        quality_meta = result_data.get("quality") or {}

        shared_meta = {
            "district": analysis_meta.get("district"),
            "before_start": analysis_meta.get("before_start"),
            "before_end": analysis_meta.get("before_end"),
            "after_start": analysis_meta.get("after_start"),
            "after_end": analysis_meta.get("after_end"),
            "before_date": before_meta.get("date"),
            "after_date": after_meta.get("date"),
            "net_change_km2": change_meta.get("net_change_km2"),
            "quality_status": quality_meta.get("status"),
            "satellite": "Sentinel-2 Harmonized",
            "analysis_type": "water-change",
        }

        # Water loss
        loss_gj, loss_cnt, loss_rep = repair_feature_collection(gj_data.get("loss") or {"type": "FeatureCollection", "features": []})
        layers["water_loss"] = {
            "geojson": loss_gj,
            "metadata": {**shared_meta, "layer_type": "loss", "area_km2": change_meta.get("loss_area_km2"), "feature_count": loss_cnt, "repaired_geometries": loss_rep},
            "allow_spatial": True,
        }

        # Water gain
        gain_gj, gain_cnt, gain_rep = repair_feature_collection(gj_data.get("gain") or {"type": "FeatureCollection", "features": []})
        layers["water_gain"] = {
            "geojson": gain_gj,
            "metadata": {**shared_meta, "layer_type": "gain", "area_km2": change_meta.get("gain_area_km2"), "feature_count": gain_cnt, "repaired_geometries": gain_rep},
            "allow_spatial": True,
        }

        # Stable water
        stable_gj, stable_cnt, stable_rep = repair_feature_collection(gj_data.get("stable") or {"type": "FeatureCollection", "features": []})
        layers["water_stable"] = {
            "geojson": stable_gj,
            "metadata": {**shared_meta, "layer_type": "stable", "area_km2": change_meta.get("stable_area_km2"), "feature_count": stable_cnt, "repaired_geometries": stable_rep},
            "allow_spatial": True,
        }

    elif analysis_type == "flood":
        flood_gj = result_data.get("flood_geojson") or {"type": "FeatureCollection", "features": []}
        clean_gj, total, repaired = repair_feature_collection(flood_gj)
        quality = result_data.get("data_quality") or {}
        if isinstance(quality, dict):
            q_status = quality.get("status", "UNKNOWN")
        else:
            q_status = str(quality)

        layers["flood_extent"] = {
            "geojson": clean_gj,
            "metadata": {
                "district": result_data.get("district"),
                "satellite": result_data.get("satellite", "Sentinel-1 SAR"),
                "polarization": result_data.get("polarization", "VV"),
                "orbit_direction": result_data.get("orbit_direction"),
                "before_date": result_data.get("before_date"),
                "after_date": result_data.get("after_date"),
                "sar_threshold_db": result_data.get("sar_threshold_db"),
                "potential_flood_area_km2": result_data.get("potential_flood_area_km2"),
                "permanent_water_area_km2": result_data.get("permanent_water_area_km2"),
                "flood_indicator": result_data.get("flood_indicator"),
                "data_quality": q_status,
                "analysis_type": "flood",
                "feature_count": total,
                "repaired_geometries": repaired,
            },
            "allow_spatial": True,
        }

    elif analysis_type == "drought":
        # Drought has NO vector spatial layer — stats CSV export only
        layers["drought_stats"] = {
            "geojson": {"type": "FeatureCollection", "features": []},
            "stats": {
                "district": result_data.get("district"),
                "satellite": result_data.get("satellite", "Sentinel-2"),
                "current_date": result_data.get("current_date"),
                "current_water_km2": result_data.get("current_water_km2"),
                "historical_water_km2": result_data.get("historical_water_km2"),
                "water_area_anomaly_percent": result_data.get("water_area_anomaly_percent"),
                "ndwi_anomaly": result_data.get("ndwi_anomaly"),
                "ndvi_anomaly_percent": result_data.get("ndvi_anomaly_percent"),
                "rainfall_30d_anomaly_percent": result_data.get("rainfall_30d_anomaly_percent"),
                "rainfall_90d_anomaly_percent": result_data.get("rainfall_90d_anomaly_percent"),
                "drought_indicator": result_data.get("drought_indicator"),
                "data_quality": (result_data.get("data_quality") or {}).get("status") if isinstance(result_data.get("data_quality"), dict) else "UNKNOWN",
                "analysis_type": "drought",
            },
            "metadata": {
                "district": result_data.get("district"),
                "analysis_type": "drought",
            },
            "allow_spatial": False,
        }

    else:
        raise ValueError(f"Unsupported analysis type: {analysis_type}")

    return layers


# =========================================================
# EXPORT FORMAT GENERATORS
# =========================================================

def export_geojson(layers_dict: Dict[str, Dict[str, Any]], target_layer: str = "all") -> bytes:
    """
    Generates single RFC 7946 GeoJSON byte payload.
    If target_layer == "all", merges features from all spatial layers into one FeatureCollection.
    """
    combined_features = []
    metadata_summary = {}

    for layer_name, layer_info in layers_dict.items():
        if not layer_info["allow_spatial"]:
            continue

        if target_layer != "all" and layer_name != target_layer:
            continue

        features = layer_info["geojson"].get("features", [])
        for feat in features:
            props = dict(feat.get("properties", {}))
            props["layer"] = layer_name
            # Copy layer metadata into properties if missing
            for meta_k, meta_v in layer_info["metadata"].items():
                if meta_k not in props and isinstance(meta_v, (str, int, float, bool)):
                    props[meta_k] = meta_v

            combined_features.append({
                "type": "Feature",
                "geometry": feat["geometry"],
                "properties": props,
            })

        metadata_summary[layer_name] = layer_info["metadata"]

    output_dict = {
        "type": "FeatureCollection",
        "name": f"AquaDetect_Export_{target_layer}",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "metadata": metadata_summary,
        "features": combined_features,
    }

    return json_dumps_bytes(output_dict)


def export_geopackage(layers_dict: Dict[str, Dict[str, Any]], target_layer: str = "all") -> bytes:
    """
    Generates a multi-layer GeoPackage (.gpkg) file.
    Tries GeoPandas + pyogrio first; falls back to pure Python sqlite3 if GDAL C-libraries are blocked.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            written_layers = 0
            for layer_name, layer_info in layers_dict.items():
                if not layer_info["allow_spatial"]:
                    continue

                if target_layer != "all" and layer_name != target_layer:
                    continue

                features = layer_info["geojson"].get("features", [])
                if not features:
                    gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
                else:
                    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

                for meta_k, meta_v in layer_info["metadata"].items():
                    if isinstance(meta_v, (str, int, float, bool)) and meta_k not in gdf.columns:
                        gdf[meta_k] = meta_v

                try:
                    gdf.to_file(tmp_path, layer=layer_name, driver="GPKG", engine="pyogrio")
                except Exception:
                    gdf.to_file(tmp_path, layer=layer_name, driver="GPKG")

                written_layers += 1

            if written_layers == 0:
                gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
                gdf.to_file(tmp_path, layer="empty_export", driver="GPKG")

            with open(tmp_path, "rb") as f:
                content = f.read()

            return content

        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning(f"GeoPandas GPKG export failed ({exc}). Using pure-Python sqlite3 fallback.")
        return _export_geopackage_sqlite(layers_dict, target_layer)


def _export_geopackage_sqlite(layers_dict: Dict[str, Dict[str, Any]], target_layer: str = "all") -> bytes:
    """
    Pure Python fallback for GeoPackage (.gpkg) file creation using built-in sqlite3 and shapely.
    Does not require GDAL/pyogrio/fiona DLLs.
    """
    import sqlite3
    import struct
    import re

    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        conn = sqlite3.connect(tmp_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
                srs_name TEXT NOT NULL,
                srs_id INTEGER NOT NULL PRIMARY KEY,
                organization TEXT NOT NULL,
                organization_coordsys_id INTEGER NOT NULL,
                definition TEXT NOT NULL,
                description TEXT
            );
        """)
        c.execute("""
            INSERT OR REPLACE INTO gpkg_spatial_ref_sys VALUES (
                'Undefined Cartesian', -1, 'NONE', -1, 'undefined', 'undefined cartesian SRS'
            ), (
                'Undefined Geographic', 0, 'NONE', 0, 'undefined', 'undefined geographic SRS'
            ), (
                'WGS 84', 4326, 'EPSG', 4326, 
                'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
                'longitude/latitude coordinates in degrees'
            );
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS gpkg_contents (
                table_name TEXT NOT NULL PRIMARY KEY,
                data_type TEXT NOT NULL,
                identifier TEXT,
                description TEXT,
                last_change TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                min_x REAL, min_y REAL, max_x REAL, max_y REAL,
                srs_id INTEGER
            );
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                geometry_type_name TEXT NOT NULL,
                srs_id INTEGER NOT NULL,
                z INTEGER NOT NULL,
                m INTEGER NOT NULL,
                CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name)
            );
        """)

        for layer_name, layer_info in layers_dict.items():
            if not layer_info["allow_spatial"]:
                continue
            if target_layer != "all" and layer_name != target_layer:
                continue

            features = layer_info["geojson"].get("features", [])
            safe_table_name = re.sub(r'[^a-zA-Z0-9_]', '_', layer_name)

            prop_keys = []
            for feat in features:
                for k in feat.get("properties", {}).keys():
                    safe_k = re.sub(r'[^a-zA-Z0-9_]', '_', k)
                    if safe_k not in prop_keys:
                        prop_keys.append(safe_k)

            col_defs = ["fid INTEGER PRIMARY KEY AUTOINCREMENT", "geom BLOB"]
            for k in prop_keys:
                col_defs.append(f'"{k}" TEXT')

            c.execute(f'CREATE TABLE "{safe_table_name}" ({", ".join(col_defs)});')

            min_x, min_y, max_x, max_y = 180.0, 90.0, -180.0, -90.0
            geom_type = "POLYGON"

            for feat in features:
                geom_dict = feat.get("geometry")
                props = feat.get("properties", {})

                gpkg_blob = None
                if geom_dict:
                    try:
                        g = shape(geom_dict)
                        if not g.is_empty:
                            geom_type = g.geom_type.upper()
                            bounds = g.bounds
                            min_x = min(min_x, bounds[0])
                            min_y = min(min_y, bounds[1])
                            max_x = max(max_x, bounds[2])
                            max_y = max(max_y, bounds[3])

                            header = b"GP\x00\x00" + struct.pack("<i", 4326)
                            gpkg_blob = header + g.wkb
                    except Exception:
                        pass

                vals = [gpkg_blob] + [str(props.get(k, "")) if props.get(k) is not None else None for k in prop_keys]
                placeholders = ", ".join(["?"] * len(vals))
                cols_str = ", ".join(['"geom"'] + [f'"{k}"' for k in prop_keys])
                c.execute(f'INSERT INTO "{safe_table_name}" ({cols_str}) VALUES ({placeholders})', vals)

            if min_x > max_x:
                min_x, min_y, max_x, max_y = 0.0, 0.0, 0.0, 0.0

            c.execute("""
                INSERT OR REPLACE INTO gpkg_contents 
                (table_name, data_type, identifier, description, min_x, min_y, max_x, max_y, srs_id)
                VALUES (?, 'features', ?, ?, ?, ?, ?, ?, 4326)
            """, (safe_table_name, safe_table_name, f"AquaDetect {layer_name} layer", min_x, min_y, max_x, max_y))

            c.execute("""
                INSERT OR REPLACE INTO gpkg_geometry_columns
                (table_name, column_name, geometry_type_name, srs_id, z, m)
                VALUES (?, 'geom', ?, 4326, 0, 0)
            """, (safe_table_name, geom_type))

        conn.commit()
        conn.close()

        with open(tmp_path, "rb") as f:
            return f.read()

    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def export_shapefile_zip(layers_dict: Dict[str, Dict[str, Any]], target_layer: str = "all") -> bytes:
    """
    Generates a Shapefile ZIP archive containing .shp, .shx, .dbf, .prj for layers.
    Truncates column names to <=10 chars using SHP_FIELD_MAPPINGS.
    Tries GeoPandas + pyogrio first; falls back to pure Python pyshp if GDAL C-libraries are blocked.
    """
    try:
        temp_dir = tempfile.mkdtemp()
        zip_buffer = io.BytesIO()

        try:
            written_shapefiles = 0

            for layer_name, layer_info in layers_dict.items():
                if not layer_info["allow_spatial"]:
                    continue

                if target_layer != "all" and layer_name != target_layer:
                    continue

                features = layer_info["geojson"].get("features", [])
                if features:
                    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
                else:
                    gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

                col_rename = {}
                for col in gdf.columns:
                    if col == "geometry":
                        continue
                    if col in SHP_FIELD_MAPPINGS:
                        col_rename[col] = SHP_FIELD_MAPPINGS[col]
                    elif len(col) > 10:
                        col_rename[col] = col[:10]

                gdf = gdf.rename(columns=col_rename)

                shp_path = os.path.join(temp_dir, f"{layer_name}.shp")
                try:
                    gdf.to_file(shp_path, driver="ESRI Shapefile", engine="pyogrio")
                except Exception:
                    gdf.to_file(shp_path, driver="ESRI Shapefile")

                written_shapefiles += 1

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_path, temp_dir)
                        zf.write(full_path, arcname=arcname)

            zip_buffer.seek(0)
            return zip_buffer.getvalue()

        finally:
            for root, dirs, files in os.walk(temp_dir, topdown=False):
                for file in files:
                    os.remove(os.path.join(root, file))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))
            os.rmdir(temp_dir)

    except Exception as exc:
        logger.warning(f"GeoPandas Shapefile export failed ({exc}). Using pure-Python pyshp fallback.")
        return _export_shapefile_pyshp(layers_dict, target_layer)


def _export_shapefile_pyshp(layers_dict: Dict[str, Dict[str, Any]], target_layer: str = "all") -> bytes:
    """
    Pure Python fallback for Shapefile ZIP generation using pyshp library.
    Does not require GDAL/Fiona/pyogrio native C-libraries or DLLs.
    """
    import shapefile

    temp_dir = tempfile.mkdtemp()
    zip_buffer = io.BytesIO()

    WGS84_PRJ = (
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
    )

    try:
        for layer_name, layer_info in layers_dict.items():
            if not layer_info["allow_spatial"]:
                continue
            if target_layer != "all" and layer_name != target_layer:
                continue

            features = layer_info["geojson"].get("features", [])
            base_path = os.path.join(temp_dir, layer_name)
            
            w = shapefile.Writer(base_path, shapeType=shapefile.POLYGON)

            field_keys = []
            for feat in features:
                props = feat.get("properties", {})
                for k in props.keys():
                    if k not in field_keys:
                        field_keys.append(k)

            dbf_fields = []
            for fk in field_keys:
                field_name = SHP_FIELD_MAPPINGS.get(fk, fk[:10] if len(fk) > 10 else fk)
                w.field(field_name, "C", size=254)
                dbf_fields.append(fk)

            if not dbf_fields:
                w.field("id", "N")

            for feat in features:
                geom = feat.get("geometry")
                props = feat.get("properties", {})

                if geom and geom.get("coordinates"):
                    try:
                        w.shape(geom)
                    except Exception:
                        w.null()
                else:
                    w.null()

                if dbf_fields:
                    rec_vals = [str(props.get(fk, "")) for fk in dbf_fields]
                    w.record(*rec_vals)
                else:
                    w.record(1)

            w.close()

            with open(f"{base_path}.prj", "w") as prj_file:
                prj_file.write(WGS84_PRJ)

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, temp_dir)
                    zf.write(full_path, arcname=arcname)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    finally:
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for file in files:
                os.remove(os.path.join(root, file))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(temp_dir)



def export_csv(layers_dict: Dict[str, Dict[str, Any]], target_layer: str = "all") -> bytes:
    """
    Generates CSV statistics/attribute payload.
    Supports tabular features + drought index statistics.
    """
    rows = []

    for layer_name, layer_info in layers_dict.items():
        if target_layer != "all" and layer_name != target_layer:
            continue

        # Handle non-spatial stats (e.g., Drought)
        if "stats" in layer_info:
            stats_row = dict(layer_info["stats"])
            stats_row["layer"] = layer_name
            rows.append(stats_row)
            continue

        features = layer_info["geojson"].get("features", [])
        for idx, feat in enumerate(features):
            props = dict(feat.get("properties", {}))
            props["feature_id"] = idx + 1
            props["layer"] = layer_name

            # Extract centroid lat/lon if geometry present
            geom_dict = feat.get("geometry")
            if geom_dict:
                try:
                    g = shape(geom_dict)
                    if not g.is_empty:
                        centroid = g.centroid
                        props["centroid_lon"] = round(float(centroid.x), 6)
                        props["centroid_lat"] = round(float(centroid.y), 6)
                        props["geometry_type"] = g.geom_type
                except Exception:
                    pass

            # Attach layer metadata
            for meta_k, meta_v in layer_info["metadata"].items():
                if isinstance(meta_v, (str, int, float, bool)) and meta_k not in props:
                    props[meta_k] = meta_v

            rows.append(props)

    if not rows:
        df = pd.DataFrame([{"message": "No feature data available for export"}])
    else:
        df = pd.DataFrame(rows)

    return df.to_csv(index=False).encode("utf-8")


def json_dumps_bytes(obj: Any) -> bytes:
    import json
    return json.dumps(obj, default=str, indent=2).encode("utf-8")
