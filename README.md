# 🌊 AquaDetect — Water-Body Analysis & Detection Platform

AquaDetect is a high-performance web application designed for interactive water-body analysis and satellite-based water detection. The application provides two coexisting workflows: **District Analysis** for exploring pre-processed district-level water body polygons, and **Image Analysis** for processing uploaded multispectral GeoTIFF imagery using the Normalized Difference Water Index (NDWI).

---

## 📌 Table of Contents
- [Overview](#overview)
- [Approach](#approach)
  - [1. District Analysis Workflow](#1-district-analysis-workflow)
  - [2. Image Analysis (NDWI) Workflow](#2-image-analysis-ndwi-workflow)
- [Data Used](#data-used)
- [Limitations](#limitations)
- [Project Architecture & Tech Stack](#project-architecture--tech-stack)
- [API Endpoints](#api-endpoints)
- [How to Run](#how-to-run)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)

---

## 🔍 Overview

AquaDetect combines geospatial frontend interactive mapping with Python raster processing pipelines in the backend.

### Key Features
- **Dual Analysis Modes**: Seamlessly toggle between **District Analysis** and **Image Analysis**.
- **Interactive Map Engine**: Built on Leaflet / React-Leaflet with custom navy-blue polygon styling and dynamic fit-bounds.
- **Strict Band Metadata Inspection**: Inspects uploaded GeoTIFFs without assuming band order based solely on band counts. Auto-detects Green (B3) and NIR (B8) bands when metadata is present, while enforcing explicit band selection when metadata is ambiguous.
- **NDWI Water Detection**: Computes per-pixel NDWI, cleans noise using morphological operations, and converts binary masks into clean GeoJSON polygons.
- **On-Demand OSM Named Identification**: Clicking any water polygon (district or NDWI-detected) triggers an OpenStreetMap Overpass lookup to identify official water body names (e.g., lakes, reservoirs, rivers).
- **Hover Statistics Card**: Displays area ($km^2$), latitude, longitude, and mean NDWI score instantly on mouse hover without triggering external API calls.

---

## 🛠️ Approach

### 1. District Analysis Workflow
1. **District Selection**: The user selects a district from the dropdown menu.
2. **GeoJSON Loading**: The frontend fetches pre-computed district GeoJSON data containing water body boundaries.
3. **Interactive Rendering**: Polygons are rendered on the map with styled vectors (`#0B3D91` stroke, `#1565C0` fill).
4. **Turf.js Geodesic Area Calculation**: Polygon areas and bounding boxes are calculated client-side using `@turf/area` and `@turf/bbox`.
5. **On-Click Name Lookup**: Clicking a polygon sends its centroid coordinates to the backend `POST /osm/water-name` endpoint, querying OpenStreetMap to discover its official name.

### 2. Image Analysis (NDWI) Workflow
1. **Spectral Band Metadata Inspection**:
   - The user uploads a multispectral GeoTIFF (`.tif` / `.tiff`).
   - The backend `POST /water/inspect-bands` uses `rasterio` to inspect band descriptions and color interpretations.
   - Using substring matching (`b3`, `green`, `b8`, `nir`), the service attempts to automatically pair the Green and NIR spectral bands.
   - If auto-detection succeeds, Green and NIR band indices are preselected. If metadata is absent or ambiguous, the UI requires explicit user band selection before enabling the **Detect Water** button.

2. **NDWI Mathematical Calculation**:
   $$\text{NDWI} = \frac{\text{Green} - \text{NIR}}{\text{Green} + \text{NIR}}$$
   - Division by zero and NaN values are handled safely (`np.errstate`).
   - Per-pixel NDWI values are thresholded against a user-adjustable parameter (default `0.30`, range `-1.0` to `+1.0`).

3. **Noise Reduction & Morphological Cleaning**:
   - `scipy.ndimage.binary_opening` removes small isolated pixel noise (e.g., sensor artifact specks).
   - `scipy.ndimage.binary_closing` fills tiny gaps and interior holes within continuous water bodies.

4. **Polygonization & Spatial Metrics**:
   - Binary masks are converted to vector shapes using `rasterio.features.shapes`.
   - Polygon geometries are projected to WGS84 (EPSG:4326).
   - Shapely computes geodesic surface area ($m^2$ and $km^2$) and spatial centroids (`centroid_lat`, `centroid_lon`).

5. **Map Rendering & OSM Integration**:
   - The resulting GeoJSON FeatureCollection is transmitted to the frontend.
   - Map automatically fits bounds to the detected water features.
   - Hovering displays area, lat, lon, and mean NDWI score.
   - Clicking triggers the same OpenStreetMap endpoint to check for known names. (An NDWI polygon remains a valid detection even if OSM has no listed name).

---

## 📊 Data Used

1. **Sentinel-2 L2A Satellite Imagery**:
   - **Green Band (Band 3 ~560nm)**: High reflectance for water bodies and vegetation.
   - **Near-Infrared / NIR (Band 8 ~842nm)**: Strongly absorbed by water, creating high contrast against vegetation and soil.
2. **GeoTIFF Multispectral Rasters**:
   - Standard single or multi-band GeoTIFF files exported from Sentinel Hub, Google Earth Engine, or QGIS.
3. **GeoJSON Boundaries**:
   - District-level water body polygons encoded in WGS84 (`EPSG:4326`).
4. **OpenStreetMap Data**:
   - Overpass API and Nominatim queries for water feature tags (`natural=water`, `waterway=riverbank`, `landuse=reservoir`).

---

## ⚠️ Limitations

1. **Cloud & Shadow Contamination**:
   - Optical satellite bands (Green/NIR) cannot penetrate thick clouds. Dark cloud shadows or steep mountain terrain shadows can occasionally yield positive NDWI values.
2. **Band Metadata Dependence**:
   - If an uploaded GeoTIFF lacks embedded band descriptions and uses non-standard band ordering, automatic detection cannot determine spectral bands, requiring manual user input.
3. **Memory & Raster File Size**:
   - Very large GeoTIFF files (>100MB) require substantial server RAM during array processing and vector polygonization.
4. **OpenStreetMap Naming Coverage**:
   - Small rural ponds, agricultural tanks, or seasonal streams may not exist in OpenStreetMap databases. These features are displayed as `"Unnamed water body"`, but remain valid NDWI detections.
5. **Turbidity & Shallow Water Sensitivity**:
   - Extremely turbid water (high sediment load) or shallow water with dense algal blooms may require lowering the NDWI threshold below `0.30` for accurate extraction.

---

## 🏗️ Project Architecture & Tech Stack

### Frontend
- **Framework**: React 18 (Vite)
- **Map Library**: Leaflet & React-Leaflet
- **Geospatial Utilities**: `@turf/area`, `@turf/bbox`
- **UI Components**: Material UI (MUI) & Custom CSS design tokens

### Backend
- **Framework**: FastAPI (Python 3.9+)
- **Raster Processing**: `rasterio`, `numpy`
- **Morphological Cleaning**: `scipy.ndimage`
- **Vector Analysis**: `shapely`, `pyproj`
- **Server**: Uvicorn

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server health check |
| `POST` | `/osm/water-name` | OpenStreetMap lookup for water body name at `(lat, lon)` |
| `POST` | `/water/inspect-bands` | Inspects uploaded GeoTIFF metadata for Green and NIR bands |
| `POST` | `/water/detect-ndwi` | Performs NDWI calculation, cleaning, and polygonization |

---

## 🚀 How to Run

### Prerequisites
- **Python 3.9+**
- **Node.js 18+** and **npm**

---

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the FastAPI backend server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   The backend API will be available at `http://127.0.0.1:8000`. API docs can be accessed at `http://127.0.0.1:8000/docs`.

---

### Frontend Setup

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install Node.js packages:
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```

4. Open your browser and navigate to `http://localhost:5173`.
