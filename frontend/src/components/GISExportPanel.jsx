/**
 * GISExportPanel.jsx — AquaDetect Production-Quality GIS Export Panel
 * ====================================================================
 *
 * Supports exporting real analysis outputs to:
 * - GeoPackage (.gpkg)
 * - GeoJSON (.geojson)
 * - ESRI Shapefile (.zip)
 * - CSV (.csv)
 *
 * Reuses actual results from last performed District, NDWI, Water Change,
 * Flood, and Drought analyses. No dummy/fabricated values.
 */

import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const ANALYSIS_OPTIONS = [
  { id: "district",     label: "District Water Bodies", icon: "🗺" },
  { id: "ndwi",         label: "Dynamic Image Analysis", icon: "🛰" },
  { id: "water-change", label: "Water Change Analysis", icon: "💧" },
  { id: "flood",        label: "Flood Risk Analysis",   icon: "🌊" },
  { id: "drought",      label: "Drought Risk Analysis", icon: "☀" },
];

const FORMAT_OPTIONS = [
  { id: "geopackage", label: "GeoPackage (.gpkg)", desc: "Multi-layer GIS format (QGIS/ArcGIS)", recommended: true, spatialOnly: true },
  { id: "geojson",    label: "GeoJSON (.geojson)", desc: "Standard web vector interchange (EPSG:4326)", spatialOnly: true },
  { id: "shapefile",  label: "Shapefile (.zip)",   desc: "ESRI Shapefile package with .prj & DBF mapping", spatialOnly: true },
  { id: "csv",        label: "CSV (.csv)",         desc: "Tabular attributes & statistical summary", spatialOnly: false },
];

// Helper to normalize analysis mode keys
function getResultKey(id) {
  if (id === "ndwi") return "image"; // MapView uses "image" key internally for NDWI result
  if (id === "water-change") return "change"; // MapView uses "change" key
  return id;
}

export default function GISExportPanel({ lastResults = {}, selectedDistrictName = "Madurai" }) {
  // Find first available analysis result to pre-select
  const findInitialAnalysis = () => {
    for (const opt of ANALYSIS_OPTIONS) {
      const key = getResultKey(opt.id);
      if (lastResults[key] || lastResults[opt.id]) {
        return opt.id;
      }
    }
    return "district";
  };

  const [selectedAnalysis, setSelectedAnalysis] = useState(findInitialAnalysis());
  const [selectedFormat, setSelectedFormat] = useState("geopackage");
  const [selectedLayer, setSelectedLayer] = useState("all");
  const [isExporting, setIsExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState(null);
  const [exportError, setExportError] = useState(null);

  // Update selected analysis if current selection has no data but another does
  useEffect(() => {
    const currentKey = getResultKey(selectedAnalysis);
    const hasData = lastResults[currentKey] || lastResults[selectedAnalysis];
    if (!hasData) {
      const init = findInitialAnalysis();
      if (init !== selectedAnalysis) {
        setSelectedAnalysis(init);
      }
    }
  }, [lastResults]);

  // Adjust format if spatial is disabled for current analysis (e.g. Drought)
  useEffect(() => {
    if (selectedAnalysis === "drought" && selectedFormat !== "csv") {
      setSelectedFormat("csv");
    }
  }, [selectedAnalysis]);

  const activeResultKey = getResultKey(selectedAnalysis);
  const activeResultData = lastResults[activeResultKey] || lastResults[selectedAnalysis];

  // Helper to extract layers list for current analysis
  const getAvailableLayers = () => {
    if (selectedAnalysis === "water-change") {
      return [
        { id: "all", label: "All Change Layers (Combined)" },
        { id: "water_loss", label: "🔴 Water Loss" },
        { id: "water_gain", label: "🟢 Water Gain" },
        { id: "water_stable", label: "🔵 Stable Water" },
      ];
    }
    return [{ id: "all", label: "All Layers" }];
  };

  // Helper to compute summary info from result data
  const getSummaryInfo = () => {
    if (!activeResultData) return null;

    let source = "AquaDetect Dataset";
    let dates = "N/A";
    let featureCount = 0;
    let areaKm2 = null;
    let quality = "HIGH";

    if (selectedAnalysis === "district") {
      source = activeResultData.source || "Static Water Database";
      featureCount = activeResultData.geojson?.features?.length || 0;
    } else if (selectedAnalysis === "ndwi") {
      source = activeResultData.satellite_source || "Sentinel-2";
      featureCount = activeResultData.geojson?.features?.length || 0;
      areaKm2 = activeResultData.statistics?.total_water_area_km2;
      quality = activeResultData.statistics?.detection_quality || "HIGH";
    } else if (selectedAnalysis === "water-change") {
      source = "Sentinel-2 Harmonized";
      const bDate = activeResultData.before?.date || activeResultData.analysis?.before_start;
      const aDate = activeResultData.after?.date || activeResultData.analysis?.after_end;
      dates = `${bDate || "Before"} → ${aDate || "After"}`;
      const lossCnt = activeResultData.geojson?.loss?.features?.length || 0;
      const gainCnt = activeResultData.geojson?.gain?.features?.length || 0;
      const stableCnt = activeResultData.geojson?.stable?.features?.length || 0;
      featureCount = lossCnt + gainCnt + stableCnt;
      areaKm2 = activeResultData.change?.net_change_km2;
      quality = activeResultData.quality?.status || "HIGH";
    } else if (selectedAnalysis === "flood") {
      source = `${activeResultData.satellite || "Sentinel-1"} ${activeResultData.polarization || "VV"}`;
      const bDate = activeResultData.before_date;
      const aDate = activeResultData.after_date;
      dates = `${bDate} → ${aDate}`;
      featureCount = activeResultData.flood_geojson?.features?.length || 0;
      areaKm2 = activeResultData.potential_flood_area_km2;
      quality = (typeof activeResultData.data_quality === "object")
        ? activeResultData.data_quality.status
        : (activeResultData.data_quality || "HIGH");
    } else if (selectedAnalysis === "drought") {
      source = "Sentinel-2 + CHIRPS";
      dates = activeResultData.current_date || "Current Season";
      areaKm2 = activeResultData.water_area_anomaly_percent;
      quality = activeResultData.data_quality?.status || "HIGH";
    }

    return { source, dates, featureCount, areaKm2, quality };
  };

  const summary = getSummaryInfo();

  // Export Trigger Handler
  const handleExport = async () => {
    if (!activeResultData) {
      setExportError("No valid result data found for the selected analysis. Please run the analysis first.");
      return;
    }

    setIsExporting(true);
    setExportError(null);
    setExportSuccess(null);

    try {
      // 1. POST /gis/export/prepare
      const prepareResp = await fetch(`${API_BASE}/gis/export/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analysis_type: selectedAnalysis,
          result_data: activeResultData,
          target_layer: selectedLayer,
        }),
      });

      if (!prepareResp.ok) {
        const errJson = await prepareResp.json();
        throw new Error(errJson.detail || "Failed to prepare GIS export.");
      }

      const prepData = await prepareResp.json();
      const exportId = prepData.export_id;

      // 2. Trigger Download GET /gis/export/download/{export_id}
      const downloadUrl = `${API_BASE}/gis/export/download/${exportId}?format=${selectedFormat}&layer=${selectedLayer}`;
      
      // Directly navigate to the download URL. 
      // The backend sends Content-Disposition: attachment, so the browser will download it directly
      // into the actual Downloads folder with the correct filename, instead of a blob UUID.
      window.location.assign(downloadUrl);

      setExportSuccess({
        format: selectedFormat.toUpperCase(),
        totalFeatures: prepData.total_features,
        message: "Download started successfully! Check your browser downloads.",
      });

    } catch (err) {
      setExportError(err.message || "An unexpected error occurred during GIS export.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div style={{ fontSize: "13px", color: "#1E293B" }}>
      {/* Title Header */}
      <div style={{ marginBottom: "16px" }}>
        <h2 style={{ fontSize: "16px", fontWeight: 800, color: "#0B3D91", margin: "0 0 4px 0" }}>
          📥 GIS Export Engine
        </h2>
        <div style={{ fontSize: "11px", color: "#64748B" }}>
          Export real spatial datasets to QGIS & ArcGIS compatible formats (EPSG:4326).
        </div>
      </div>

      {/* Analysis Status Grid */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", textTransform: "uppercase", marginBottom: "6px", letterSpacing: "0.4px" }}>
          Available Analysis Outputs
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {ANALYSIS_OPTIONS.map((opt) => {
            const key = getResultKey(opt.id);
            const data = lastResults[key] || lastResults[opt.id];
            const isSelected = selectedAnalysis === opt.id;
            const isDrought = opt.id === "drought";

            let statusLabel = "Not Run Yet";
            let statusBg = "#F1F5F9";
            let statusColor = "#64748B";

            if (data) {
              if (isDrought) {
                statusLabel = "Stats Only (Vector N/A)";
                statusBg = "#FEF3C7";
                statusColor = "#B45309";
              } else {
                statusLabel = "✓ Ready";
                statusBg = "#DCFCE7";
                statusColor = "#15803D";
              }
            }

            return (
              <button
                key={opt.id}
                onClick={() => {
                  if (data) setSelectedAnalysis(opt.id);
                }}
                disabled={!data}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 12px",
                  borderRadius: "8px",
                  border: isSelected ? "2px solid #0B3D91" : "1px solid #E2E8F0",
                  background: isSelected ? "#EFF6FF" : data ? "#FFFFFF" : "#F8FAFC",
                  cursor: data ? "pointer" : "not-allowed",
                  opacity: data ? 1 : 0.65,
                  textAlign: "left",
                  transition: "all 0.15s",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "15px" }}>{opt.icon}</span>
                  <span style={{ fontWeight: isSelected ? 700 : 600, fontSize: "12px", color: isSelected ? "#0B3D91" : "#1E293B" }}>
                    {opt.label}
                  </span>
                </div>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: "12px",
                    backgroundColor: statusBg,
                    color: statusColor,
                  }}
                >
                  {statusLabel}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Analysis Information Summary Card */}
      {summary && (
        <div
          style={{
            background: "#F8FAFC",
            border: "1px solid #CBD5E1",
            borderRadius: "8px",
            padding: "10px 12px",
            marginBottom: "16px",
            fontSize: "11px",
          }}
        >
          <div style={{ fontWeight: 700, color: "#0B3D91", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.4px" }}>
            Dataset Summary — {selectedAnalysis.toUpperCase()}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
            <div>
              <span style={{ color: "#64748B" }}>Source: </span>
              <span style={{ fontWeight: 600 }}>{summary.source}</span>
            </div>
            <div>
              <span style={{ color: "#64748B" }}>CRS: </span>
              <span style={{ fontWeight: 600 }}>EPSG:4326 (WGS84)</span>
            </div>
            {summary.dates !== "N/A" && (
              <div>
                <span style={{ color: "#64748B" }}>Observation: </span>
                <span style={{ fontWeight: 600 }}>{summary.dates}</span>
              </div>
            )}
            {selectedAnalysis !== "drought" && (
              <div>
                <span style={{ color: "#64748B" }}>Features: </span>
                <span style={{ fontWeight: 600 }}>{summary.featureCount} polygons</span>
              </div>
            )}
            {summary.areaKm2 !== null && (
              <div>
                <span style={{ color: "#64748B" }}>{selectedAnalysis === "drought" ? "Area Anomaly: " : "Area: "}</span>
                <span style={{ fontWeight: 600 }}>
                  {typeof summary.areaKm2 === "number" ? summary.areaKm2.toFixed(2) : summary.areaKm2} {selectedAnalysis === "drought" ? "%" : "km²"}
                </span>
              </div>
            )}
            <div>
              <span style={{ color: "#64748B" }}>Quality: </span>
              <span style={{ fontWeight: 700, color: summary.quality === "HIGH" ? "#16A34A" : "#D97706" }}>
                {summary.quality}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Layer Selector (Water Change only) */}
      {selectedAnalysis === "water-change" && (
        <div style={{ marginBottom: "14px" }}>
          <label style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>
            Select Layer
          </label>
          <select
            value={selectedLayer}
            onChange={(e) => setSelectedLayer(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: "6px",
              border: "1px solid #CBD5E1",
              fontSize: "12px",
              backgroundColor: "#FFF",
            }}
          >
            {getAvailableLayers().map((l) => (
              <option key={l.id} value={l.id}>
                {l.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Export Format Selector */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", textTransform: "uppercase", marginBottom: "6px", letterSpacing: "0.4px" }}>
          Export Format
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {FORMAT_OPTIONS.map((fmt) => {
            const isSelected = selectedFormat === fmt.id;
            const isSpatialDisabled = selectedAnalysis === "drought" && fmt.spatialOnly;

            return (
              <button
                key={fmt.id}
                onClick={() => {
                  if (!isSpatialDisabled) setSelectedFormat(fmt.id);
                }}
                disabled={isSpatialDisabled}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  padding: "9px 12px",
                  borderRadius: "8px",
                  border: isSelected ? "2px solid #0B3D91" : "1px solid #CBD5E1",
                  background: isSelected ? "#EFF6FF" : isSpatialDisabled ? "#F1F5F9" : "#FFFFFF",
                  cursor: isSpatialDisabled ? "not-allowed" : "pointer",
                  opacity: isSpatialDisabled ? 0.5 : 1,
                  textAlign: "left",
                  transition: "all 0.15s",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px", width: "100%" }}>
                  <span style={{ fontWeight: 700, fontSize: "12px", color: isSelected ? "#0B3D91" : "#1E293B" }}>
                    {fmt.label}
                  </span>
                  {fmt.recommended && !isSpatialDisabled && (
                    <span style={{ fontSize: "9px", fontWeight: 800, backgroundColor: "#0B3D91", color: "#FFF", padding: "1px 6px", borderRadius: "10px", marginLeft: "auto" }}>
                      RECOMMENDED
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "10px", color: "#64748B", marginTop: "2px" }}>
                  {fmt.desc}
                </div>
              </button>
            );
          })}
        </div>

        {/* Drought Warning Notice */}
        {selectedAnalysis === "drought" && (
          <div style={{ marginTop: "8px", padding: "8px 10px", backgroundColor: "#FEF3C7", borderRadius: "6px", color: "#92400E", fontSize: "11px", lineHeight: "1.4" }}>
            ⚠️ <strong>Spatial Vector Export Unavailable:</strong> Drought Analysis outputs environmental indicators and statistical anomalies rather than polygon geometries. CSV format is enabled.
          </div>
        )}

        {/* GeoTIFF Notice */}
        <div style={{ marginTop: "8px", fontSize: "10px", color: "#64748B", fontStyle: "italic" }}>
          ℹ️ GeoTIFF export is unavailable for GEE analyses because layers are rendered as server-side satellite tiles rather than a downloadable raster file.
        </div>
      </div>

      {/* Error & Success Messages */}
      {exportError && (
        <div style={{ marginBottom: "12px", padding: "10px", backgroundColor: "#FEE2E2", color: "#B91C1C", borderRadius: "6px", fontSize: "11px" }}>
          ❌ {exportError}
        </div>
      )}

      {exportSuccess && (
        <div style={{ marginBottom: "12px", padding: "10px", backgroundColor: "#DCFCE7", color: "#15803D", borderRadius: "6px", fontSize: "11px" }}>
          ✅ <strong>{exportSuccess.format} Export Ready:</strong> {exportSuccess.message}
        </div>
      )}

      {/* Download Action Button */}
      <button
        onClick={handleExport}
        disabled={isExporting || !activeResultData}
        style={{
          width: "100%",
          padding: "12px",
          borderRadius: "8px",
          border: "none",
          background: isExporting || !activeResultData ? "#94A3B8" : "linear-gradient(135deg, #0B3D91, #1565C0)",
          color: "#FFF",
          fontWeight: 700,
          fontSize: "13px",
          cursor: isExporting || !activeResultData ? "not-allowed" : "pointer",
          boxShadow: isExporting || !activeResultData ? "none" : "0 3px 10px rgba(11, 61, 145, 0.3)",
          transition: "all 0.2s",
        }}
      >
        {isExporting ? "⏳ Preparing GIS Dataset..." : "📥 Download GIS Dataset"}
      </button>
    </div>
  );
}
