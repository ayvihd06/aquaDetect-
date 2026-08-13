"""
main.py — AquaDetect FastAPI Application Entry Point
=====================================================

This is the root application file for the AquaDetect backend API.

It is responsible for:
  1. Creating the FastAPI application instance.
  2. Registering all routers (hydrology, GIS export, and inline routes).
  3. Configuring CORS middleware for the React frontend (Vite dev server).
  4. Defining request/response models for inline API endpoints.
  5. Exposing all HTTP endpoints for analysis features.

Architecture overview:
  ┌────────────────────────────────────────────────────────────────┐
  │  Frontend (React/Vite, localhost:5173)                        │
  │        │                                                       │
  │        ▼  HTTP (JSON)                                          │
  │  FastAPI Application (main.py)                                │
  │   ├── /water/...       NDWI, Change Detection                 │
  │   ├── /osm/...         OpenStreetMap Naming                    │
  │   ├── /water/flood-... Flood Risk (Sentinel-1 SAR)            │
  │   ├── /water/drought-. Drought Risk (Sentinel-2 + CHIRPS)     │
  │   └── /gis/...         GIS Export (GeoPackage, SHP, GeoJSON)  │
  └────────────────────────────────────────────────────────────────┘
"""

from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Core GEE-based water detection (used by /water/detect endpoint)
from app.services.earth_engine import detect_water

# OpenStreetMap Overpass API lookup for official water body names
from app.services.openstreetmap import (
    find_nearby_water_body,
)

# Local GeoTIFF NDWI pipeline (band inspection + detection)
from app.services.ndwi_service import (
    inspect_raster_bands,
    process_ndwi_image,
    MAX_FILE_SIZE_BYTES,
)

# GEE-based Sentinel-2 water change detection pipeline
from app.services.change_detection import (
    compare_water_extent_ee,
    process_geotiff_change_detection,
)

# Separate routers for hydrology (flood + drought) and GIS export
from app.routes.hydrology import router as hydrology_router
from app.routes.gis_export import router as gis_export_router

# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="AquaDetect API",
    version="1.0.0",
    description=(
        "Satellite-powered water body analysis API. "
        "Supports NDWI detection, Sentinel-2 water change, "
        "Sentinel-1 SAR flood risk, Sentinel-2 drought risk, "
        "OpenStreetMap water naming, and GIS file export."
    ),
)

# Hydrology & GIS Export Routers
app.include_router(hydrology_router)
app.include_router(gis_export_router)


# =========================================================
# CORS — Allow React frontend to call the backend
# =========================================================

# Allow all origins — public API accessible from any frontend (Vercel, Render, localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],   # Allow all HTTP verbs (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],   # Allow all request headers
)



# =========================================================
# REQUEST MODELS
# =========================================================

class DetectionRequest(BaseModel):
    latitude: float
    longitude: float

class OSMRequest(BaseModel):
    latitude: float
    longitude: float

class WaterCompareRequest(BaseModel):
    district: str
    comparison_type: str = "same_season"
    before_year: int = 2023
    after_year: int = 2026
    season: str = "jun_aug"
    before_start: Optional[str] = None
    before_end: Optional[str] = None
    after_start: Optional[str] = None
    after_end: Optional[str] = None
    max_cloud_cover: float = 20.0
    threshold: float = 0.30
    debug: bool = False


# =========================================================
# BASIC ROUTES
# =========================================================

@app.get("/")
def root():

    return {
        "message": "AquaDetect API is running"
    }


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# =========================================================
# WATER DETECTION
# =========================================================

@app.post("/detect")
def detect(
    request: DetectionRequest
):

    result = detect_water(
        latitude=request.latitude,
        longitude=request.longitude,
    )

    return result

@app.post("/osm/water-name")
def get_water_body_name(
    request: OSMRequest,
):

    try:

        result = find_nearby_water_body(
            latitude=request.latitude,
            longitude=request.longitude,
        )

        return result

    except Exception as error:

        return {
            "found": False,
            "name": None,
            "error": str(error),
        }


# =========================================================
# WATER — INSPECT BANDS
# =========================================================

@app.post("/water/inspect-bands")
async def inspect_bands(
    image: UploadFile = File(...),
):
    """
    Read a GeoTIFF upload and return band information.
    Identifies Green / NIR bands from metadata if possible.
    DOES NOT perform any NDWI calculation.
    """

    # ---- File type check ----
    if not (image.filename or "").lower().endswith((".tif", ".tiff")):
        raise HTTPException(
            status_code=422,
            detail="Invalid file type. Please upload a GeoTIFF (.tif / .tiff).",
        )

    file_bytes = await image.read()

    # ---- File size check ----
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                "The uploaded image is too large. "
                "Please use a smaller area or supported resolution."
            ),
        )

    try:
        result = inspect_raster_bands(file_bytes)
        return result

    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))

    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail="Water detection failed. Please check the uploaded image and try again.",
        )


# =========================================================
# WATER — NDWI DETECTION
# =========================================================

@app.post("/water/detect-ndwi")
async def detect_ndwi(
    image:          UploadFile = File(...),
    threshold:      float      = Form(0.30),
    green_band:     int        = Form(...),
    nir_band:       int        = Form(...),
    threshold_mode: str        = Form("manual"),
    debug:          bool       = Form(False),
):
    """
    Detect water bodies from a multispectral GeoTIFF using NDWI.

    Required form fields:
        image           : GeoTIFF file
        threshold       : NDWI threshold when mode=manual (default 0.30)
        green_band      : 1-based index of the Green spectral band
        nir_band        : 1-based index of the NIR spectral band
        threshold_mode  : "manual" | "adaptive" (default "manual")
        debug           : Include extra diagnostic info (default False)

    Returns GeoJSON FeatureCollection + full scientific statistics.
    """

    # ---- File type check ----
    if not (image.filename or "").lower().endswith((".tif", ".tiff")):
        raise HTTPException(
            status_code=422,
            detail="Invalid file type. Please upload a GeoTIFF (.tif / .tiff).",
        )

    file_bytes = await image.read()

    # ---- File size check ----
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The uploaded image is too large.",
        )

    # ---- Threshold range ----
    if not (-1.0 <= threshold <= 1.0):
        raise HTTPException(
            status_code=422,
            detail="Threshold must be between -1.0 and 1.0.",
        )

    if threshold_mode not in ("manual", "adaptive"):
        threshold_mode = "manual"

    try:
        result = process_ndwi_image(
            file_bytes=file_bytes,
            threshold=threshold,
            green_band=green_band,
            nir_band=nir_band,
            threshold_mode=threshold_mode,
            debug=debug,
        )
        return result

    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))

    except RuntimeError as err:
        raise HTTPException(status_code=500, detail=str(err))

    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail="Water detection failed. Please check the uploaded image and try again.",
        )


# =========================================================
# WATER CHANGE ANALYSIS (EARTH ENGINE SENTINEL-2)
# =========================================================

@app.post("/water/compare-ndwi")
def compare_ndwi(request: WaterCompareRequest):
    """
    Perform temporal water extent change detection between two observation periods
    for a specified district using Earth Engine Sentinel-2 imagery.
    """
    if not request.district or not request.district.strip():
        raise HTTPException(
            status_code=422,
            detail="District name is required for water change analysis.",
        )

    if not (-1.0 <= request.threshold <= 1.0):
        raise HTTPException(
            status_code=422,
            detail="Threshold must be between -1.0 and 1.0.",
        )

    if not (0.0 <= request.max_cloud_cover <= 100.0):
        raise HTTPException(
            status_code=422,
            detail="Maximum cloud cover must be between 0.0 and 100.0.",
        )

    try:
        result = compare_water_extent_ee(
            district=request.district,
            comparison_type=request.comparison_type,
            before_year=request.before_year,
            after_year=request.after_year,
            season=request.season,
            before_start=request.before_start,
            before_end=request.before_end,
            after_start=request.after_start,
            after_end=request.after_end,
            max_cloud_cover=request.max_cloud_cover,
            threshold=request.threshold,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=422,
                detail=result.get("error", "Water change analysis failed due to imagery availability."),
            )

        return result

    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail=f"Water change analysis failed: {str(err)}",
        )


# =========================================================
# WATER CHANGE ANALYSIS (DUAL GEOTIFF FALLBACK)
# =========================================================

@app.post("/water/compare-geotiff")
async def compare_geotiff(
    before_image: UploadFile = File(...),
    after_image:  UploadFile = File(...),
    threshold:    float      = Form(0.30),
    before_green: int        = Form(1),
    before_nir:   int        = Form(2),
    after_green:  int        = Form(1),
    after_nir:    int        = Form(2),
):
    """
    Perform temporal water change detection using two uploaded GeoTIFF rasters.
    Aligns 'after' raster to 'before' raster spatial grid using rasterio warp.
    """
    for img in (before_image, after_image):
        if not (img.filename or "").lower().endswith((".tif", ".tiff")):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid file type for {img.filename}. Please upload GeoTIFF (.tif / .tiff).",
            )

    before_bytes = await before_image.read()
    after_bytes  = await after_image.read()

    if len(before_bytes) > MAX_FILE_SIZE_BYTES or len(after_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="One or both uploaded images exceed the maximum allowed file size.",
        )

    try:
        result = process_geotiff_change_detection(
            before_bytes=before_bytes,
            after_bytes=after_bytes,
            threshold=threshold,
            before_green=before_green,
            before_nir=before_nir,
            after_green=after_green,
            after_nir=after_nir,
        )
        return result
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail=f"GeoTIFF change analysis failed: {str(err)}",
        )