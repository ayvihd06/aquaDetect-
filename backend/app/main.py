from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.services.earth_engine import detect_water
from app.services.openstreetmap import (
    find_nearby_water_body,
)
from app.services.ndwi_service import (
    inspect_raster_bands,
    process_ndwi_image,
    MAX_FILE_SIZE_BYTES,
)

# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="AquaDetect API",
    version="1.0.0",
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# REQUEST MODEL
# =========================================================

class DetectionRequest(BaseModel):
    latitude: float
    longitude: float

class OSMRequest(BaseModel):
    latitude: float
    longitude: float

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
    image:      UploadFile = File(...),
    threshold:  float      = Form(0.30),
    green_band: int        = Form(...),
    nir_band:   int        = Form(...),
):
    """
    Detect water bodies from a multispectral GeoTIFF using NDWI.

    Required form fields:
        image       : GeoTIFF file
        threshold   : NDWI threshold (default 0.30)
        green_band  : 1-based index of the Green spectral band
        nir_band    : 1-based index of the NIR spectral band

    Returns GeoJSON FeatureCollection + statistics.
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

    # ---- Threshold range ----
    if not (-1.0 <= threshold <= 1.0):
        raise HTTPException(
            status_code=422,
            detail="Threshold must be between -1.0 and 1.0.",
        )

    try:
        result = process_ndwi_image(
            file_bytes=file_bytes,
            threshold=threshold,
            green_band=green_band,
            nir_band=nir_band,
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