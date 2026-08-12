# 🌊 AquaDetect — Satellite Water Intelligence Platform

AquaDetect is a **production-quality geospatial intelligence web application** for satellite-based water body analysis across Tamil Nadu districts. It uses real multispectral satellite imagery from **Sentinel-1** and **Sentinel-2**, combined with **Google Earth Engine**, to detect, analyze, and export water-related spatial data in formats compatible with professional GIS software.

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Analysis Features](#-analysis-features)
  - [1. District Analysis](#1-district-analysis)
  - [2. NDWI Image Analysis](#2-ndwi-image-analysis)
  - [3. Water Change Analysis](#3-water-change-analysis)
  - [4. Flood Risk Analysis](#4-flood-risk-analysis)
  - [5. Drought Risk Analysis](#5-drought-risk-analysis)
  - [6. GIS Export](#6-gis-export)
- [Data Sources](#-data-sources)
- [Limitations](#-limitations)
- [Project Architecture & Tech Stack](#-project-architecture--tech-stack)
- [Project Structure](#-project-structure)
- [API Endpoints](#-api-endpoints)
- [How to Run](#-how-to-run)
  - [Prerequisites](#prerequisites)
  - [Google Earth Engine Setup](#-google-earth-engine--gcp-project-id-setup)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)

---

## 🔍 Overview

AquaDetect is built for environmental researchers, hydrologists, and GIS analysts who need a reliable, scientifically honest tool for monitoring water resources using satellite data. The platform presents a clean interactive map interface backed by real GEE-powered analysis pipelines — no fabricated data, no hardcoded results.

### Key Principles
- 🛰️ **Real Satellite Data Only** — All analysis uses live Sentinel-1 and Sentinel-2 imagery via Google Earth Engine.
- 🔬 **Scientifically Honest** — Never fabricates geometries, statistics, dates, or metadata.
- 📐 **GIS-Compatible Exports** — All vector outputs are in EPSG:4326 (WGS84) and open correctly in QGIS and ArcGIS Pro.
- 🗺️ **Interactive** — Fully interactive Leaflet map with water body hover cards, click-to-name OSM lookups, and real-time layer switching.

---

## 🛰️ Analysis Features

### 1. District Analysis

Explore pre-computed water body polygons for any of the **38 Tamil Nadu districts**.

- **Data Source**: Static GeoJSON water body boundaries extracted from OpenStreetMap.
- **Workflow**:
  1. Select a district from the dropdown panel.
  2. The map loads all water body polygons for that district.
  3. Hover over any polygon to see area (km²), coordinates, and water body type.
  4. Click a polygon to trigger a live OpenStreetMap Overpass API lookup for its official name (e.g., "Vandiyur Lake", "Vaigai Reservoir").
- **Area Calculation**: Performed client-side using `@turf/area` on WGS84 geometry.

---

### 2. NDWI Image Analysis

Upload a multispectral GeoTIFF raster and detect water bodies using the **Normalized Difference Water Index (NDWI)**.

$$\text{NDWI} = \frac{\text{Green} - \text{NIR}}{\text{Green} + \text{NIR}}$$

- **Input**: Sentinel-2 GeoTIFF file (`.tif` / `.tiff`) with Green (B3 ~560nm) and NIR (B8 ~842nm) bands.
- **Workflow**:
  1. Upload a GeoTIFF — the backend inspects band metadata to auto-detect B3/B8.
  2. If auto-detection fails (missing metadata), the user manually selects band indices.
  3. Set the NDWI threshold (default: `0.30`, range: `-1.0` to `+1.0`).
  4. Click **Detect Water** — the backend calculates NDWI, applies morphological noise removal, and polygonizes the binary water mask into a GeoJSON FeatureCollection.
  5. Detected polygons appear on the interactive map, color-coded by NDWI value.
- **Band Detection Logic**: Inspects `rasterio` band descriptions using substring matching (`b3`, `green`, `b8`, `nir`, etc.) with fallback to manual selection if metadata is ambiguous.
- **Noise Removal**: `scipy.ndimage.binary_opening` (removes speckles) + `scipy.ndimage.binary_closing` (fills holes).
- **Vector Output**: GeoJSON polygons in WGS84, each with `area_km2`, `mean_ndwi`, `centroid_lat`, `centroid_lon`.

---

### 3. Water Change Analysis

Detect **multi-temporal water body changes** between two time periods using Sentinel-2 Surface Reflectance imagery via Google Earth Engine.

- **Satellite**: Sentinel-2 SR Harmonized (COPERNICUS/S2_SR_HARMONIZED)
- **Workflow**:
  1. Select a district and define **before** and **after** date windows.
  2. The backend queries GEE for cloud-masked Sentinel-2 composites for both periods.
  3. Water is classified by NDWI thresholding on each composite.
  4. Change detection produces three distinct spatial layers:
     - 🔴 **Water Loss** — areas that were water before but are not now
     - 🟢 **Water Gain** — areas that became water in the after period
     - 🔵 **Stable Water** — areas that remained water in both periods
  5. Results are displayed as separate colored map layers with area statistics.
- **Output**: Three GeoJSON FeatureCollections with `change_type`, `before_water`, `after_water`, area, and date metadata.

---

### 4. Flood Risk Analysis

Detect **potential flood extent** using **Sentinel-1 C-band SAR (Synthetic Aperture Radar)** imagery. SAR is unique because it penetrates cloud cover, making it ideal for monitoring active flood events.

- **Satellite**: Sentinel-1 GRD (COPERNICUS/S1_GRD), VV polarization
- **Methodology**:
  - Compares pre-event and post-event SAR backscatter images.
  - Applies absolute VV backscatter threshold (< threshold dB, based on Twele et al. 2016) to classify open water.
  - Subtracts permanent water bodies (JRC Global Surface Water) from flood candidates.
  - Applies connected pixel count filter to remove noise.
- **Flood Logic**: `NEW_FLOOD = after_water AND NOT before_water AND NOT permanent_water`
- **Rainfall Correlation**: Integrates CHIRPS daily rainfall data to cross-validate flood indicators.
- **Output**:
  - `flood_geojson`: GeoJSON FeatureCollection of flood candidate polygons.
  - `flood_indicator`: Classification (NONE / LOW / MODERATE / HIGH).
  - `data_quality`: Coverage and quality assessment.
  - Visual map tile layers: pre-SAR, post-SAR, SAR change, flood extent.
- **Disclaimer**: Flood extent is a satellite-derived indicator; not an official flood warning. Field verification required.

---

### 5. Drought Risk Analysis

Monitor **multi-indicator drought conditions** using Sentinel-2 optical imagery and CHIRPS rainfall data via Google Earth Engine.

- **Satellites**: Sentinel-2 SR Harmonized + UCSB-CHG/CHIRPS/DAILY
- **Drought Indicators** (multi-pillar scoring):
  - **Water Area Anomaly** — Current water extent vs. historical seasonal baseline.
  - **NDWI Anomaly** — Change in mean NDWI vs. historical mean.
  - **NDVI Anomaly** — Vegetation health change (NDVI = (B8-B4)/(B8+B4)).
  - **30-Day Rainfall Anomaly** — Rainfall deficit vs. historical 30-day baseline.
  - **90-Day Rainfall Anomaly** — Longer-term cumulative rainfall deficit.
- **Historical Baseline**: Same calendar window from past years (configurable, default: 5 years).
- **Drought Indicator Classification**: NORMAL / WATCH / WARNING / SEVERE / EXTREME
- **Tile Outputs**: Current RGB, current NDWI, current NDVI, current water mask map tiles.
- **Note**: Drought analysis produces statistical indicators and raster tiles — not vector polygons. Spatial GIS export for Drought is therefore unavailable; CSV statistics export is supported.

---

### 6. GIS Export

Export real analysis results into industry-standard GIS formats compatible with **QGIS** and **ArcGIS Pro**.

- **Supported Formats**:
  | Format | Extension | Best For |
  |---|---|---|
  | GeoPackage | `.gpkg` | Multi-layer professional GIS format (Recommended) |
  | GeoJSON | `.geojson` | Web GIS, open interchange |
  | ESRI Shapefile | `.zip` | Legacy GIS software (DBF 10-char field names auto-mapped) |
  | CSV | `.csv` | Statistics, spreadsheets, tabular analysis |

- **Layer Naming**:
  | Analysis | GeoPackage Layers |
  |---|---|
  | District | `district_water` |
  | NDWI | `ndwi_water` |
  | Water Change | `water_loss`, `water_gain`, `water_stable` |
  | Flood Risk | `flood_extent` |
  | Drought | *(CSV statistics only — no vector geometry)* |

- **Scientific Integrity Rules**:
  - ❌ No fabricated polygons, invented coordinates, or fake metadata.
  - ❌ GeoTIFF export is disabled for GEE analyses (visualization tiles ≠ downloadable rasters).
  - ✅ Geometry repair via `shapely.make_valid()` is applied silently before export.
  - ✅ All exports are EPSG:4326 (WGS84) with embedded CRS information.
  - ✅ Shapefile DBF field names automatically truncated to ≤10 characters.

- **Export Flow**:
  1. Run any analysis in AquaDetect.
  2. Navigate to **GIS Export** in the top navbar.
  3. Select the analysis, layer, and format.
  4. Click **Download GIS Dataset** — the file downloads directly to your browser's Downloads folder.

---

## 📊 Data Sources

| Dataset | Source | Usage |
|---|---|---|
| Sentinel-2 SR Harmonized | ESA / Google Earth Engine | NDWI, Water Change, Drought |
| Sentinel-1 GRD (SAR) | ESA / Google Earth Engine | Flood Risk Detection |
| CHIRPS Daily Rainfall | UCSB-CHG / Google Earth Engine | Flood & Drought Rainfall Anomaly |
| JRC Global Surface Water | Pekel et al. 2016 / Google Earth Engine | Permanent water mask (Flood) |
| OpenStreetMap | Overpass API / Nominatim | Water body naming |
| Static District GeoJSON | OpenStreetMap extracted | District water body boundaries |

---

## ⚠️ Limitations

1. **Cloud Cover (Optical Sensors)**: Sentinel-2 (optical) cannot penetrate thick clouds. Cloud shadow can occasionally produce false positive NDWI detections. Sentinel-1 SAR is cloud-independent.
2. **GEE Quota and Latency**: Complex analyses using Google Earth Engine can take 15–60 seconds depending on the study area and server load.
3. **No GeoTIFF Raster Download**: GEE-based analyses produce server-rendered visualization tiles rather than downloadable rasters. GeoTIFF export is only available for locally-uploaded NDWI files.
4. **Band Metadata Dependence**: If an uploaded GeoTIFF lacks embedded band descriptions, the user must manually select Green and NIR band indices.
5. **OpenStreetMap Coverage**: Small ponds, agricultural tanks, or seasonal streams may not be named in OpenStreetMap.
6. **Drought Vector Export Unavailable**: Drought analysis produces statistical indicators and map tiles only — no vector polygon geometry is produced, and therefore spatial vector export is not available.
7. **Large Raster Files**: GeoTIFF files over 100 MB may require significant server RAM during processing.

---

## 🏗️ Project Architecture & Tech Stack

### Frontend
| Component | Technology |
|---|---|
| Framework | React 18 (Vite) |
| Map Engine | Leaflet + React-Leaflet |
| Spatial Utilities | `@turf/area`, `@turf/bbox` |
| UI Components | Material UI (MUI) + Custom CSS |
| HTTP Client | Native `fetch` API |

### Backend
| Component | Technology |
|---|---|
| Web Framework | FastAPI (Python 3.9+) |
| Satellite Processing | Google Earth Engine Python API (`earthengine-api`) |
| Raster Processing | `rasterio`, `numpy` |
| Morphological Cleaning | `scipy.ndimage` |
| Geometry & CRS | `shapely`, `pyproj`, `geopandas` |
| GIS File Export | `geopandas`, `pyogrio` (GeoPackage, Shapefile, GeoJSON, CSV) |
| Server | Uvicorn (ASGI) |

---

## 📁 Project Structure

```
aquadetect/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI application entry point
│   │   ├── routes/
│   │   │   ├── hydrology.py               # Flood & Drought API routes
│   │   │   └── gis_export.py              # GIS Export prepare & download routes
│   │   └── services/
│   │       ├── earth_engine.py            # GEE initialization & tile helpers
│   │       ├── ndwi_service.py            # Local GeoTIFF NDWI detection pipeline
│   │       ├── water_detection.py         # Shared water classification helpers
│   │       ├── change_detection.py        # Sentinel-2 GEE water change pipeline
│   │       ├── gis_export_service.py      # GIS export adapters & file generators
│   │       ├── openstreetmap.py           # OSM Overpass water name lookup
│   │       ├── osm_cache.py               # OSM results caching
│   │       ├── osm_enrichment.py          # Water body property enrichment
│   │       └── hydrology/
│   │           ├── flood_detection.py     # Sentinel-1 SAR flood pipeline
│   │           ├── drought_detection.py   # Sentinel-2 + CHIRPS drought pipeline
│   │           └── hydrology_config.py    # Shared hydrology constants & thresholds
│   ├── requirements.txt                   # Python dependencies
│   └── test_gis_export.py                 # Automated GIS export test suite
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Navbar.jsx                 # Top navigation bar (all 6 modes)
│       │   ├── MapView.jsx                # Interactive Leaflet map + panel routing
│       │   ├── ImageAnalysisPanel.jsx     # NDWI local GeoTIFF upload & detection UI
│       │   ├── WaterChangePanel.jsx       # Sentinel-2 water change analysis UI
│       │   ├── HydrologyPanel.jsx         # Flood & Drought monitoring UI
│       │   ├── GISExportPanel.jsx         # GIS Export format & download UI
│       │   └── Sidebar.jsx                # District/water body info sidebar
│       └── pages/
│           └── Home.jsx                   # Root page layout
│
└── README.md
```

---

## 🔌 API Endpoints

### Core Water Analysis
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server health check |
| `POST` | `/osm/water-name` | OSM Overpass lookup: official name at `(lat, lon)` |
| `POST` | `/water/inspect-bands` | Inspect uploaded GeoTIFF for Green/NIR bands |
| `POST` | `/water/detect-ndwi` | NDWI detection, noise removal, polygonization |
| `POST` | `/water/compare-ndwi` | Sentinel-2 GEE water change detection |

### Hydrology (Flood & Drought)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/water/flood-analysis` | Sentinel-1 SAR flood detection + CHIRPS rainfall |
| `POST` | `/water/drought-analysis` | Sentinel-2 + CHIRPS drought risk indicators |

### GIS Export
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/gis/export/prepare` | Validate & cache analysis result; returns `export_id` |
| `GET` | `/gis/export/download/{export_id}` | Download GeoJSON / GeoPackage / Shapefile ZIP / CSV |

**Full interactive API documentation** is available at `http://127.0.0.1:8000/docs` when the backend is running.

---

## 🚀 How to Run

### Prerequisites
- **Python 3.9+**
- **Node.js 18+** and **npm**
- **Google Earth Engine Account** (free for research — required for Flood, Drought, and Water Change)
- A **Google Cloud Project ID** with the Earth Engine API enabled

---

### 🌍 Google Earth Engine & GCP Project ID Setup

#### Step 1: Sign Up for Google Earth Engine
Visit [earthengine.google.com/signup](https://earthengine.google.com/signup/) and register with a Google account. Select **Non-commercial** or **Research** access.

#### Step 2: Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click **New Project** and create a project (e.g., `AquaDetect`).
3. Note your **Project ID** (e.g., `aquadetect-504614`).

#### Step 3: Enable the Earth Engine API
In the Cloud Console, navigate to **APIs & Services → Library**, search for **"Google Earth Engine API"**, and click **Enable**.

#### Step 4: Authenticate in Your Terminal
```bash
earthengine authenticate
```
Follow the browser prompt and sign in with your Google account.

#### Step 5: Set Your Project ID
Open [`backend/app/services/earth_engine.py`](./backend/app/services/earth_engine.py) and update:
```python
PROJECT_ID = "your-gcp-project-id"   # e.g., "aquadetect-504614"
```

---

### Backend Setup

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Create a virtual environment
python -m venv venv

# 3. Activate the virtual environment
# Windows (PowerShell):
.\\venv\\Scripts\\Activate
# Linux / macOS:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Authenticate Earth Engine (if not done already)
earthengine authenticate

# 6. Start the backend server
uvicorn app.main:app --reload --port 8000
```

The backend will be live at: `http://127.0.0.1:8000`  
API documentation: `http://127.0.0.1:8000/docs`

---

### Frontend Setup

```bash
# 1. Open a new terminal and navigate to the frontend directory
cd frontend

# 2. Install Node.js packages
npm install

# 3. Start the Vite development server
npm run dev
```

Open your browser and navigate to: **`http://localhost:5173`**

---

### Running Tests (Backend)

```bash
cd backend
python -m pytest test_gis_export.py -v
```

This runs the GIS Export test suite which verifies:
- GeoJSON validity and feature count
- GeoPackage multi-layer structure (openable in GeoPandas / QGIS)
- Shapefile ZIP components and DBF ≤10-char field names
- Drought spatial export rejection + CSV statistics export
- Geometry repair via `shapely.make_valid()`
- API endpoint prepare/download flow

---

## 🎯 Supported Districts

AquaDetect supports all **38 districts of Tamil Nadu**, including:

Ariyalur, Chennai, Coimbatore, Cuddalore, Dharmapuri, Dindigul, Erode, Kancheepuram, Kanniyakumari, Karur, Madurai, Nagapattinam, Namakkal, Nilgiris, Perambalur, Pudukkottai, Ramanathapuram, Salem, Sivaganga, Thanjavur, Theni, Thiruvallur, Thiruvarur, Tirunelveli, Tiruppur, Tiruvallur, Tirvannamalai, Vellore, Villupuram, Virudhunagar.

---

## 📄 License

This project is intended for academic, research, and non-commercial use. Satellite imagery is sourced via Google Earth Engine and is subject to the [Google Earth Engine Terms of Service](https://earthengine.google.com/terms/).
