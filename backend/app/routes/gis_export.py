"""
gis_export.py — GIS Export API Router for AquaDetect
=====================================================

Endpoints:
  POST /gis/export/prepare  — Accepts analysis result JSON, validates, caches, returns export_id
  GET  /gis/export/download/{export_id} — Generates & streams GeoJSON, GeoPackage, Shapefile ZIP, or CSV

No dummy values. Reuses exact analysis outputs.
"""

import json
import logging
import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, validator

from app.services.gis_export_service import (
    extract_export_layers,
    export_cache,
    export_geojson,
    export_geopackage,
    export_shapefile_zip,
    export_csv,
    MAX_PAYLOAD_BYTES,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class GISExportPrepareRequest(BaseModel):
    analysis_type: str
    result_data: Dict[str, Any]
    target_layer: Optional[str] = "all"

    @validator("analysis_type")
    def validate_analysis_type(cls, v):
        allowed = ("district", "ndwi", "image", "water-change", "change", "flood", "drought")
        v_clean = v.strip().lower()
        if v_clean not in allowed:
            raise ValueError(f"Invalid analysis_type '{v}'. Allowed: {', '.join(allowed)}")
        return v_clean


def _sanitize_filename(name: str) -> str:
    """Removes unsafe characters for HTTP Content-Disposition filename."""
    return re.sub(r'[^a-zA-Z0-9_\-.]', '_', name)


@router.post("/gis/export/prepare")
def prepare_gis_export(request: GISExportPrepareRequest):
    """
    Validates analysis result JSON, repairs invalid geometries, and caches payload for export.
    Returns export_id and summary metadata.
    """
    # Payload size check
    raw_str = json.dumps(request.result_data, default=str)
    if len(raw_str.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The analysis result payload is too large to export (max 50 MB allowed).",
        )

    try:
        layers = extract_export_layers(request.analysis_type, request.result_data)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    except Exception as err:
        logger.error("Failed to extract GIS export layers: %s", err, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to prepare GIS export dataset.")

    # Calculate totals
    total_features = 0
    repaired_count = 0
    allow_spatial = False
    layer_names = list(layers.keys())

    for l_name, l_info in layers.items():
        if l_info.get("allow_spatial"):
            allow_spatial = True
            feat_cnt = l_info["metadata"].get("feature_count", 0)
            total_features += feat_cnt
            repaired_count += l_info["metadata"].get("repaired_geometries", 0)

    district_name = request.result_data.get("district") or "AquaDetect"
    export_payload = {
        "analysis_type": request.analysis_type,
        "district": district_name,
        "layers": layers,
        "layer_names": layer_names,
        "allow_spatial": allow_spatial,
        "total_features": total_features,
        "repaired_geometries": repaired_count,
    }

    export_id = export_cache.store(export_payload)

    return {
        "success": True,
        "export_id": export_id,
        "analysis_type": request.analysis_type,
        "district": district_name,
        "layer_names": layer_names,
        "allow_spatial": allow_spatial,
        "total_features": total_features,
        "repaired_geometries": repaired_count,
        "message": "GIS Export dataset ready for download." if allow_spatial else "Dataset prepared. Spatial export unavailable for Drought; CSV export enabled.",
    }


@router.get("/gis/export/download/{export_id}")
def download_gis_export(
    export_id: str,
    format: str = Query("geopackage", regex="^(geojson|geopackage|shapefile|csv)$"),
    layer: str = Query("all"),
):
    """
    Generates and streams requested GIS file format.
    Formats: 'geojson' | 'geopackage' | 'shapefile' | 'csv'
    """
    cached = export_cache.get(export_id)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="Export session expired or invalid. Please re-run export preparation.",
        )

    analysis_type = cached["analysis_type"]
    district = cached.get("district", "AquaDetect")
    layers = cached["layers"]
    allow_spatial = cached["allow_spatial"]

    # Reject spatial format request if analysis has no spatial features (e.g. Drought)
    if format in ("geojson", "geopackage", "shapefile") and not allow_spatial:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Spatial vector export ({format}) is unavailable because this analysis "
                "does not produce vector geometries. Please select CSV format to export statistical indicators."
            ),
        )

    safe_district = _sanitize_filename(district.capitalize())
    safe_analysis = _sanitize_filename(analysis_type.replace("-", "_").capitalize())

    try:
        if format == "geojson":
            content = export_geojson(layers, target_layer=layer)
            filename = f"AquaDetect_{safe_district}_{safe_analysis}.geojson"
            media_type = "application/geo+json"

        elif format == "geopackage":
            content = export_geopackage(layers, target_layer=layer)
            filename = f"AquaDetect_{safe_district}_{safe_analysis}.gpkg"
            media_type = "application/geopackage+sqlite3"

        elif format == "shapefile":
            content = export_shapefile_zip(layers, target_layer=layer)
            filename = f"AquaDetect_{safe_district}_{safe_analysis}_Shapefile.zip"
            media_type = "application/zip"

        elif format == "csv":
            content = export_csv(layers, target_layer=layer)
            filename = f"AquaDetect_{safe_district}_{safe_analysis}_Stats.csv"
            media_type = "text/csv"

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'.")

        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    except HTTPException:
        raise
    except Exception as err:
        logger.error("GIS file generation error: %s", err, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate {format.upper()} export file: {str(err)}",
        )
