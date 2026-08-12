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
    Generates a multi-layer GeoPackage (.gpkg) file using GeoPandas + pyogrio.
    """
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
                # Write empty GeoDataFrame schema if no features
                gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            else:
                gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

            # Attach metadata as layer columns if scalar
            for meta_k, meta_v in layer_info["metadata"].items():
                if isinstance(meta_v, (str, int, float, bool)) and meta_k not in gdf.columns:
                    gdf[meta_k] = meta_v

            try:
                gdf.to_file(tmp_path, layer=layer_name, driver="GPKG", engine="pyogrio")
            except Exception as e:
                # Fallback to default engine if pyogrio has edge-case issue
                gdf.to_file(tmp_path, layer=layer_name, driver="GPKG")

            written_layers += 1

        if written_layers == 0:
            # Fallback empty layer
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            gdf.to_file(tmp_path, layer="empty_export", driver="GPKG", engine="pyogrio")

        with open(tmp_path, "rb") as f:
            content = f.read()

        return content

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
    """
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

            # Column name truncation mapping for Shapefile DBF limit (10 chars)
            col_rename = {}
            for col in gdf.columns:
                if col == "geometry":
                    continue
                if col in SHP_FIELD_MAPPINGS:
                    col_rename[col] = SHP_FIELD_MAPPINGS[col]
                elif len(col) > 10:
                    col_rename[col] = col[:10]

            gdf = gdf.rename(columns=col_rename)

            # Export shapefile
            shp_path = os.path.join(temp_dir, f"{layer_name}.shp")
            try:
                gdf.to_file(shp_path, driver="ESRI Shapefile", engine="pyogrio")
            except Exception:
                gdf.to_file(shp_path, driver="ESRI Shapefile")

            written_shapefiles += 1


        # Package temp_dir into ZIP
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, temp_dir)
                    zf.write(full_path, arcname=arcname)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    finally:
        # Cleanup temp directory
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
