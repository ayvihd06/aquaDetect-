import { useState, useRef, useCallback } from "react";

// =========================================================
// IMAGE ANALYSIS PANEL
// =========================================================
//
// Handles:
//   1. File drag-and-drop / browse (GeoTIFF only)
//   2. POST /water/inspect-bands  → reads band metadata
//   3. Auto-detects Green/NIR or requires explicit selection
//   4. NDWI threshold slider
//   5. POST /water/detect-ndwi
//   6. Shows statistics after detection
//   7. Calls onNdwiResult(geojson, stats) on success
// =========================================================

const API_BASE = "http://127.0.0.1:8000";

// Shared compact text styles (matching MapView panel)
const labelStyle = {
  fontSize: "12px",
  color: "#666",
  marginBottom: "4px",
};

const valueStyle = {
  fontSize: "14px",
  fontWeight: 600,
  marginBottom: "14px",
  color: "#111",
};

// =========================================================
// COMPONENT
// =========================================================

function ImageAnalysisPanel({ onNdwiResult }) {
  // -------------------------------------------------------
  // File state
  // -------------------------------------------------------
  const [file, setFile]             = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef                = useRef(null);

  // -------------------------------------------------------
  // Band inspection state
  // -------------------------------------------------------
  const [inspecting, setInspecting]   = useState(false);
  const [inspectError, setInspectError] = useState(null);
  const [bandInfo, setBandInfo]         = useState(null);
  // bandInfo = { band_count, bands: [{index, description, color_interp}],
  //              auto_green, auto_nir, auto_detected }

  // User-selected bands (when auto-detection fails)
  const [selectedGreen, setSelectedGreen] = useState("");
  const [selectedNir, setSelectedNir]     = useState("");

  // -------------------------------------------------------
  // NDWI detection state
  // -------------------------------------------------------
  const [threshold, setThreshold]   = useState(0.30);
  const [detecting, setDetecting]   = useState(false);
  const [detectError, setDetectError] = useState(null);
  const [stats, setStats]           = useState(null);


  // =========================================================
  // HELPERS
  // =========================================================

  const formatFileSize = (bytes) => {
    if (bytes < 1024)       return `${bytes} B`;
    if (bytes < 1048576)    return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const resetState = () => {
    setBandInfo(null);
    setInspectError(null);
    setDetectError(null);
    setStats(null);
    setSelectedGreen("");
    setSelectedNir("");
    if (onNdwiResult) onNdwiResult(null, null);
  };


  // =========================================================
  // FILE SELECTION
  // =========================================================

  const handleFileChosen = useCallback(async (chosen) => {
    if (!chosen) return;

    // Validate extension
    const name = chosen.name.toLowerCase();
    if (!name.endsWith(".tif") && !name.endsWith(".tiff")) {
      setInspectError(
        "Invalid file type.\nPlease upload a GeoTIFF (.tif or .tiff)."
      );
      setFile(null);
      return;
    }

    setFile(chosen);
    resetState();
    await inspectBands(chosen);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps


  const inspectBands = async (chosen) => {
    setInspecting(true);
    setInspectError(null);
    setBandInfo(null);

    try {
      const formData = new FormData();
      formData.append("image", chosen);

      const response = await fetch(
        `${API_BASE}/water/inspect-bands`,
        { method: "POST", body: formData }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail ||
          "Could not read band information from the uploaded file."
        );
      }

      const data = await response.json();
      setBandInfo(data);

      // Pre-fill selectors if auto-detected
      if (data.auto_detected) {
        setSelectedGreen(String(data.auto_green));
        setSelectedNir(String(data.auto_nir));
      }

    } catch (err) {
      setInspectError(err.message || "Failed to inspect the uploaded image.");
    } finally {
      setInspecting(false);
    }
  };


  // =========================================================
  // DRAG AND DROP
  // =========================================================

  const onDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => setIsDragging(false);

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileChosen(dropped);
  };

  const onBrowseClick = () => fileInputRef.current?.click();

  const onFileInputChange = (e) => {
    const chosen = e.target.files?.[0];
    if (chosen) handleFileChosen(chosen);
    // Reset so same file can be re-selected
    e.target.value = "";
  };


  // =========================================================
  // DETECT WATER
  // =========================================================

  const effectiveGreen = bandInfo?.auto_detected
    ? bandInfo.auto_green
    : parseInt(selectedGreen, 10) || null;

  const effectiveNir = bandInfo?.auto_detected
    ? bandInfo.auto_nir
    : parseInt(selectedNir, 10) || null;

  const canDetect =
    file &&
    bandInfo &&
    !inspecting &&
    !detecting &&
    effectiveGreen !== null &&
    effectiveNir !== null &&
    effectiveGreen !== effectiveNir;


  const handleDetect = async () => {
    if (!canDetect) return;

    setDetecting(true);
    setDetectError(null);
    setStats(null);
    if (onNdwiResult) onNdwiResult(null, null);

    try {
      const formData = new FormData();
      formData.append("image", file);
      formData.append("threshold", String(threshold));
      formData.append("green_band", String(effectiveGreen));
      formData.append("nir_band", String(effectiveNir));

      const response = await fetch(
        `${API_BASE}/water/detect-ndwi`,
        { method: "POST", body: formData }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail ||
          "Water detection failed. Please check the uploaded image and try again."
        );
      }

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || "Detection did not succeed.");
      }

      setStats(data.statistics);

      if (onNdwiResult) {
        onNdwiResult(data.geojson, data.statistics);
      }

    } catch (err) {
      setDetectError(err.message || "Water detection failed.");
    } finally {
      setDetecting(false);
    }
  };


  // =========================================================
  // RENDER
  // =========================================================

  return (
    <div>

      {/* =====================================================
          UPLOAD ZONE
          ===================================================== */}

      <div style={{ marginBottom: "14px" }}>
        <div style={{ fontSize: "13px", color: "#555", marginBottom: "8px" }}>
          Upload Satellite Image
        </div>

        {/* Drop zone */}
        <div
          onClick={onBrowseClick}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          style={{
            border: `2px dashed ${isDragging ? "#0B3D91" : "#c0cde0"}`,
            borderRadius: "8px",
            padding: "18px 12px",
            textAlign: "center",
            cursor: "pointer",
            background: isDragging ? "#edf2fb" : "#f7f9fc",
            transition: "all 0.18s",
          }}
        >
          <div style={{ fontSize: "22px", marginBottom: "6px" }}>🛰️</div>
          <div style={{ fontSize: "12px", color: "#555", lineHeight: 1.5 }}>
            <strong>Drag & drop</strong> or <strong>browse</strong>
            <br />
            GeoTIFF · TIFF · Sentinel-2 multispectral
          </div>
        </div>

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".tif,.tiff"
          style={{ display: "none" }}
          onChange={onFileInputChange}
        />
      </div>


      {/* =====================================================
          SELECTED FILE INFO
          ===================================================== */}

      {file && (
        <div
          style={{
            marginBottom: "14px",
            padding: "10px 12px",
            background: "#f0f4fa",
            borderRadius: "7px",
            fontSize: "12px",
          }}
        >
          <div style={{ fontWeight: 600, color: "#0B3D91", marginBottom: "2px" }}>
            📄 {file.name}
          </div>
          <div style={{ color: "#666" }}>
            {formatFileSize(file.size)}
          </div>
        </div>
      )}


      {/* =====================================================
          INSPECTING SPINNER
          ===================================================== */}

      {inspecting && (
        <div style={{ fontSize: "12px", color: "#555", marginBottom: "10px" }}>
          🔍 Reading band information…
        </div>
      )}


      {/* =====================================================
          INSPECT ERROR
          ===================================================== */}

      {inspectError && (
        <div
          style={{
            marginBottom: "12px",
            padding: "10px",
            borderRadius: "7px",
            background: "#fff1f1",
            color: "#b00020",
            fontSize: "12px",
            lineHeight: 1.5,
            whiteSpace: "pre-line",
          }}
        >
          ⚠️ {inspectError}
        </div>
      )}


      {/* =====================================================
          BAND INFORMATION
          ===================================================== */}

      {bandInfo && !inspecting && (
        <div style={{ marginBottom: "14px" }}>
          <div style={labelStyle}>Spectral Bands</div>

          {/* Auto-detected */}
          {bandInfo.auto_detected ? (
            <div
              style={{
                padding: "8px 10px",
                borderRadius: "6px",
                background: "#e8f5e9",
                fontSize: "12px",
                color: "#2e7d32",
                marginBottom: "4px",
              }}
            >
              ✅ Auto-detected
              <br />
              Green → Band {bandInfo.auto_green}
              {bandInfo.bands[bandInfo.auto_green - 1]?.description
                ? ` (${bandInfo.bands[bandInfo.auto_green - 1].description})`
                : ""}
              <br />
              NIR → Band {bandInfo.auto_nir}
              {bandInfo.bands[bandInfo.auto_nir - 1]?.description
                ? ` (${bandInfo.bands[bandInfo.auto_nir - 1].description})`
                : ""}
            </div>
          ) : (
            /* Manual selection required */
            <div>
              <div
                style={{
                  padding: "8px 10px",
                  borderRadius: "6px",
                  background: "#fff8e1",
                  fontSize: "12px",
                  color: "#e65100",
                  marginBottom: "10px",
                  lineHeight: 1.5,
                }}
              >
                ⚠️ Band names could not be identified from metadata.
                <br />
                Please select the Green and NIR bands manually.
              </div>

              {/* Green band selector */}
              <div style={{ marginBottom: "8px" }}>
                <div style={{ ...labelStyle, marginBottom: "4px" }}>
                  Green band (for NDWI)
                </div>
                <select
                  value={selectedGreen}
                  onChange={(e) => setSelectedGreen(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "7px 8px",
                    borderRadius: "6px",
                    border: "1px solid #d0d0d0",
                    fontSize: "12px",
                    background: "#fff",
                    boxSizing: "border-box",
                  }}
                >
                  <option value="">— select Green band —</option>
                  {bandInfo.bands.map((b) => (
                    <option key={b.index} value={String(b.index)}>
                      Band {b.index}
                      {b.description ? ` — ${b.description}` : ""}
                      {` (${b.color_interp})`}
                    </option>
                  ))}
                </select>
              </div>

              {/* NIR band selector */}
              <div style={{ marginBottom: "4px" }}>
                <div style={{ ...labelStyle, marginBottom: "4px" }}>
                  NIR band (for NDWI)
                </div>
                <select
                  value={selectedNir}
                  onChange={(e) => setSelectedNir(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "7px 8px",
                    borderRadius: "6px",
                    border: "1px solid #d0d0d0",
                    fontSize: "12px",
                    background: "#fff",
                    boxSizing: "border-box",
                  }}
                >
                  <option value="">— select NIR band —</option>
                  {bandInfo.bands
                    .filter((b) => String(b.index) !== selectedGreen)
                    .map((b) => (
                      <option key={b.index} value={String(b.index)}>
                        Band {b.index}
                        {b.description ? ` — ${b.description}` : ""}
                        {` (${b.color_interp})`}
                      </option>
                    ))}
                </select>
              </div>

              {selectedGreen && selectedNir && selectedGreen === selectedNir && (
                <div style={{ fontSize: "11px", color: "#b00020", marginTop: "4px" }}>
                  Green and NIR must be different bands.
                </div>
              )}
            </div>
          )}
        </div>
      )}


      {/* =====================================================
          NDWI THRESHOLD
          ===================================================== */}

      {bandInfo && !inspecting && (
        <div style={{ marginBottom: "16px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "6px",
            }}
          >
            <div style={labelStyle}>NDWI Threshold</div>
            <div
              style={{
                fontSize: "13px",
                fontWeight: 700,
                color: "#0B3D91",
              }}
            >
              {threshold.toFixed(2)}
            </div>
          </div>

          <input
            type="range"
            min="-1"
            max="1"
            step="0.01"
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            style={{
              width: "100%",
              accentColor: "#0B3D91",
              cursor: "pointer",
            }}
          />

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: "10px",
              color: "#999",
              marginTop: "2px",
            }}
          >
            <span>−1.0</span>
            <span>0</span>
            <span>+1.0</span>
          </div>
        </div>
      )}


      {/* =====================================================
          DETECT BUTTON
          ===================================================== */}

      {bandInfo && !inspecting && (
        <button
          onClick={handleDetect}
          disabled={!canDetect}
          style={{
            width: "100%",
            padding: "11px",
            borderRadius: "8px",
            border: "none",
            background: canDetect
              ? "linear-gradient(135deg, #0B3D91, #1565C0)"
              : "#c0cde0",
            color: canDetect ? "#fff" : "#888",
            fontSize: "13px",
            fontWeight: 700,
            cursor: canDetect ? "pointer" : "not-allowed",
            letterSpacing: "0.03em",
            transition: "opacity 0.15s",
            marginBottom: "12px",
          }}
        >
          {detecting ? "⏳ Detecting…" : "🔍 Detect Water"}
        </button>
      )}


      {/* =====================================================
          DETECTION ERROR
          ===================================================== */}

      {detectError && (
        <div
          style={{
            padding: "10px",
            borderRadius: "7px",
            background: "#fff1f1",
            color: "#b00020",
            fontSize: "12px",
            lineHeight: 1.5,
            marginBottom: "12px",
          }}
        >
          ⚠️ {detectError}
        </div>
      )}


      {/* =====================================================
          DETECTION RESULTS
          ===================================================== */}

      {stats && (
        <div
          style={{
            marginTop: "4px",
            paddingTop: "14px",
            borderTop: "1px solid #e5e5e5",
          }}
        >
          <div
            style={{
              fontSize: "13px",
              fontWeight: 700,
              color: "#2e7d32",
              marginBottom: "14px",
            }}
          >
            ✅ Detection Complete
          </div>

          {/* Water body count */}
          <div style={labelStyle}>Water Bodies Detected</div>
          <div style={valueStyle}>{stats.water_body_count}</div>

          {/* Total area */}
          <div style={labelStyle}>Total Detected Water Area</div>
          <div style={valueStyle}>{stats.total_water_area_km2.toFixed(4)} km²</div>

          {/* Largest */}
          <div style={labelStyle}>Largest Water Body</div>
          <div style={valueStyle}>{stats.largest_water_body_km2.toFixed(4)} km²</div>

          {/* Average */}
          <div style={labelStyle}>Average Water Body</div>
          <div style={{ ...valueStyle, marginBottom: 0 }}>
            {stats.average_water_body_km2.toFixed(4)} km²
          </div>
        </div>
      )}

    </div>
  );
}

export default ImageAnalysisPanel;
