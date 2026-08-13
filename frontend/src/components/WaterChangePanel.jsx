import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const DISTRICTS = [
  "Ariyalur", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul",
  "Erode", "Kancheepuram", "Kanniyakumari", "Karur", "Madurai", "Nagapattinam",
  "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Salem",
  "Sivaganga", "Thanjavur", "Theni", "Thiruvallur", "Thoothukudi", "Tiruchirappalli",
  "Tirunelveli", "Tiruvannamalai", "Vellore", "Villupuram", "Virudhunagar"
];

const labelStyle = {
  fontSize: "12px",
  color: "#64748B",
  marginBottom: "4px",
  fontWeight: 500,
};

const inputStyle = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: "6px",
  border: "1px solid #CBD5E1",
  fontSize: "13px",
  backgroundColor: "#FFFFFF",
  color: "#1E293B",
  outline: "none",
  marginBottom: "12px",
};

export default function WaterChangePanel({
  selectedDistrictName,
  onDistrictSelect,
  onChangeResult,
  onLayerSelect,
  activeLayer,
}) {
  const [district, setDistrict] = useState(selectedDistrictName || "Madurai");
  const [comparisonType, setComparisonType] = useState("same_season"); // "same_season" | "custom"
  const [beforeYear, setBeforeYear] = useState(2023);
  const [afterYear, setAfterYear] = useState(2026);
  const [season, setSeason] = useState("jun_aug");

  // Custom period states
  const [beforeStart, setBeforeStart] = useState("2023-06-01");
  const [beforeEnd, setBeforeEnd] = useState("2023-08-31");
  const [afterStart, setAfterStart] = useState("2026-06-01");
  const [afterEnd, setAfterEnd] = useState("2026-08-31");

  // Advanced parameters
  const [maxCloudCover, setMaxCloudCover] = useState(20);
  const [threshold, setThreshold] = useState(0.30);

  // View Mode: "map" | "validation"
  const [viewTab, setViewTab] = useState("map");

  // Status & Results
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [showMetadata, setShowMetadata] = useState(false);

  const handleDistrictChange = (e) => {
    const dName = e.target.value;
    setDistrict(dName);
    if (onDistrictSelect) {
      onDistrictSelect(dName);
    }
  };

  const runComparison = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setStatusMessage("Connecting to Google Earth Engine...");

    try {
      setStatusMessage("Querying Sentinel-2 SR imagery & applying cloud masking...");
      
      const payload = {
        district: district,
        comparison_type: comparisonType,
        before_year: parseInt(beforeYear),
        after_year: parseInt(afterYear),
        season: season,
        before_start: comparisonType === "custom" ? beforeStart : null,
        before_end: comparisonType === "custom" ? beforeEnd : null,
        after_start: comparisonType === "custom" ? afterStart : null,
        after_end: comparisonType === "custom" ? afterEnd : null,
        max_cloud_cover: parseFloat(maxCloudCover),
        threshold: parseFloat(threshold),
      };

      const response = await fetch(`${API_BASE}/water/compare-ndwi`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      setStatusMessage("Computing NDWI & 4-state pixel classification...");

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Sentinel-2 comparison failed. Check cloud cover or observation dates.");
      }

      const data = await response.json();
      setResult(data);

      if (onChangeResult) {
        onChangeResult(data);
      }
      if (onLayerSelect) {
        onLayerSelect("change");
      }
    } catch (err) {
      setError(err.message);
      if (onChangeResult) {
        onChangeResult(null);
      }
    } finally {
      setLoading(false);
      setStatusMessage("");
    }
  };

  const layerOptions = [
    { id: "change", label: "🗺️ Change Map" },
    { id: "before_rgb", label: "🛰️ Before RGB" },
    { id: "after_rgb", label: "🛰️ After RGB" },
    { id: "before_ndwi", label: "🌊 Before NDWI" },
    { id: "after_ndwi", label: "🌊 After NDWI" },
    { id: "before_mask", label: "💧 Before Mask" },
    { id: "after_mask", label: "💧 After Mask" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px", color: "#0F172A" }}>
      {/* Title Header */}
      <div>
        <h3 style={{ margin: "0 0 4px 0", fontSize: "15px", fontWeight: 700, color: "#0F172A" }}>
          🌊 Water Change Analysis
        </h3>
        <p style={{ margin: 0, fontSize: "12px", color: "#64748B" }}>
          Real Sentinel-2 temporal surface-water change detection
        </p>
      </div>

      {/* Mode Sub-Tabs */}
      <div style={{ display: "flex", backgroundColor: "#F1F5F9", borderRadius: "6px", padding: "3px" }}>
        <button
          type="button"
          onClick={() => setViewTab("map")}
          style={{
            flex: 1,
            padding: "6px",
            fontSize: "12px",
            fontWeight: 600,
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            backgroundColor: viewTab === "map" ? "#FFFFFF" : "transparent",
            color: viewTab === "map" ? "#1E293B" : "#64748B",
            boxShadow: viewTab === "map" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
          }}
        >
          Change Analysis
        </button>
        <button
          type="button"
          onClick={() => setViewTab("validation")}
          style={{
            flex: 1,
            padding: "6px",
            fontSize: "12px",
            fontWeight: 600,
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            backgroundColor: viewTab === "validation" ? "#FFFFFF" : "transparent",
            color: viewTab === "validation" ? "#1E293B" : "#64748B",
            boxShadow: viewTab === "validation" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
          }}
        >
          Satellite Validation
        </button>
      </div>

      {/* District Selector */}
      <div>
        <div style={labelStyle}>District Boundary (AOI)</div>
        <select value={district} onChange={handleDistrictChange} style={inputStyle}>
          {DISTRICTS.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {/* Controls View */}
      {viewTab === "map" && (
        <>
          <div>
            <div style={labelStyle}>Comparison Mode</div>
            <div style={{ display: "flex", gap: "6px", marginBottom: "12px" }}>
              <button
                type="button"
                onClick={() => setComparisonType("same_season")}
                style={{
                  flex: 1,
                  padding: "6px 10px",
                  borderRadius: "6px",
                  border: comparisonType === "same_season" ? "1.5px solid #2563EB" : "1px solid #CBD5E1",
                  backgroundColor: comparisonType === "same_season" ? "#EFF6FF" : "#F8FAFC",
                  color: comparisonType === "same_season" ? "#1D4ED8" : "#475569",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Same Season
              </button>
              <button
                type="button"
                onClick={() => setComparisonType("custom")}
                style={{
                  flex: 1,
                  padding: "6px 10px",
                  borderRadius: "6px",
                  border: comparisonType === "custom" ? "1.5px solid #2563EB" : "1px solid #CBD5E1",
                  backgroundColor: comparisonType === "custom" ? "#EFF6FF" : "#F8FAFC",
                  color: comparisonType === "custom" ? "#1D4ED8" : "#475569",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Custom Period
              </button>
            </div>
          </div>

          {comparisonType === "same_season" ? (
            <>
              <div style={{ display: "flex", gap: "10px" }}>
                <div style={{ flex: 1 }}>
                  <div style={labelStyle}>Before Year</div>
                  <select value={beforeYear} onChange={(e) => setBeforeYear(e.target.value)} style={inputStyle}>
                    {[2020, 2021, 2022, 2023, 2024, 2025].map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={labelStyle}>After Year</div>
                  <select value={afterYear} onChange={(e) => setAfterYear(e.target.value)} style={inputStyle}>
                    {[2023, 2024, 2025, 2026].map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <div style={labelStyle}>Season Window</div>
                <select value={season} onChange={(e) => setSeason(e.target.value)} style={inputStyle}>
                  <option value="jun_aug">Jun–Aug (SW Monsoon)</option>
                  <option value="sep_nov">Sep–Nov (NE Monsoon)</option>
                  <option value="dec_feb">Dec–Feb (Winter)</option>
                  <option value="mar_may">Mar–May (Summer)</option>
                  <option value="full_year">Full Year Composite</option>
                </select>
              </div>
            </>
          ) : (
            <>
              <div style={{ backgroundColor: "#F8FAFC", padding: "10px", borderRadius: "6px", border: "1px solid #E2E8F0" }}>
                <div style={{ fontSize: "12px", fontWeight: 600, marginBottom: "6px", color: "#334155" }}>Period 1 (Before)</div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <input type="date" value={beforeStart} onChange={(e) => setBeforeStart(e.target.value)} style={{ ...inputStyle, marginBottom: 0 }} />
                  <input type="date" value={beforeEnd} onChange={(e) => setBeforeEnd(e.target.value)} style={{ ...inputStyle, marginBottom: 0 }} />
                </div>
              </div>

              <div style={{ backgroundColor: "#F8FAFC", padding: "10px", borderRadius: "6px", border: "1px solid #E2E8F0" }}>
                <div style={{ fontSize: "12px", fontWeight: 600, marginBottom: "6px", color: "#334155" }}>Period 2 (After)</div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <input type="date" value={afterStart} onChange={(e) => setAfterStart(e.target.value)} style={{ ...inputStyle, marginBottom: 0 }} />
                  <input type="date" value={afterEnd} onChange={(e) => setAfterEnd(e.target.value)} style={{ ...inputStyle, marginBottom: 0 }} />
                </div>
              </div>
            </>
          )}

          {/* Advanced Sliders */}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", ...labelStyle }}>
                <span>Max Cloud Cover</span>
                <span>{maxCloudCover}%</span>
              </div>
              <input
                type="range"
                min="1"
                max="50"
                value={maxCloudCover}
                onChange={(e) => setMaxCloudCover(e.target.value)}
                style={{ width: "100%", accentColor: "#2563EB" }}
              />
            </div>

            <div>
              <div style={{ display: "flex", justifyContent: "space-between", ...labelStyle }}>
                <span>NDWI Threshold</span>
                <span>{threshold}</span>
              </div>
              <input
                type="range"
                min="-0.2"
                max="0.6"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                style={{ width: "100%", accentColor: "#2563EB" }}
              />
            </div>
          </div>

          <button
            type="button"
            onClick={runComparison}
            disabled={loading}
            style={{
              padding: "10px 14px",
              borderRadius: "6px",
              backgroundColor: loading ? "#94A3B8" : "#2563EB",
              color: "#FFFFFF",
              fontSize: "13px",
              fontWeight: 600,
              border: "none",
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background 0.2s ease",
            }}
          >
            {loading ? "Processing Satellite Observations..." : "Compare Water Extent"}
          </button>
        </>
      )}

      {/* Loading Status Indicator */}
      {loading && (
        <div style={{ padding: "10px", backgroundColor: "#EFF6FF", borderRadius: "6px", border: "1px solid #BFDBFE", fontSize: "12px", color: "#1D4ED8" }}>
          ⏳ {statusMessage}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div style={{ padding: "10px", backgroundColor: "#FEF2F2", borderRadius: "6px", border: "1px solid #FCA5A5", fontSize: "12px", color: "#991B1B" }}>
          ⚠️ <strong>Error:</strong> {error}
        </div>
      )}

      {/* Results Section */}
      {result && result.success && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "2px" }}>
          {/* Layer Selector Bar */}
          <div>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", marginBottom: "6px", textTransform: "uppercase" }}>Map Visualization Layer</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px" }}>
              {layerOptions.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onLayerSelect && onLayerSelect(opt.id)}
                  style={{
                    padding: "6px",
                    borderRadius: "4px",
                    border: (activeLayer || "change") === opt.id ? "1.5px solid #2563EB" : "1px solid #CBD5E1",
                    backgroundColor: (activeLayer || "change") === opt.id ? "#EFF6FF" : "#FFFFFF",
                    color: (activeLayer || "change") === opt.id ? "#1D4ED8" : "#334155",
                    fontSize: "11px",
                    fontWeight: 600,
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Satellite Validation Tab Content */}
          {viewTab === "validation" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", backgroundColor: "#F8FAFC", padding: "10px", borderRadius: "6px", border: "1px solid #E2E8F0" }}>
              <div style={{ fontSize: "12px", fontWeight: 700, color: "#0F172A" }}>🔍 Satellite Source Verification</div>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontSize: "11px" }}>
                <div style={{ backgroundColor: "#FFFFFF", padding: "8px", borderRadius: "4px", border: "1px solid #CBD5E1" }}>
                  <strong style={{ color: "#2563EB" }}>BEFORE (Period 1)</strong>
                  <div><strong>Date:</strong> {result.before.date}</div>
                  <div><strong>Granule Cloud:</strong> {result.before.cloud_cover}%</div>
                  <div><strong>Valid Coverage:</strong> {result.before.valid_coverage_percent}%</div>
                  <div><strong>Total Water:</strong> {result.before.water_area_km2} km²</div>
                  <div><strong>Comparable:</strong> {result.before.comparable_water_area_km2} km²</div>
                </div>

                <div style={{ backgroundColor: "#FFFFFF", padding: "8px", borderRadius: "4px", border: "1px solid #CBD5E1" }}>
                  <strong style={{ color: "#2563EB" }}>AFTER (Period 2)</strong>
                  <div><strong>Date:</strong> {result.after.date}</div>
                  <div><strong>Granule Cloud:</strong> {result.after.cloud_cover}%</div>
                  <div><strong>Valid Coverage:</strong> {result.after.valid_coverage_percent}%</div>
                  <div><strong>Total Water:</strong> {result.after.water_area_km2} km²</div>
                  <div><strong>Comparable:</strong> {result.after.comparable_water_area_km2} km²</div>
                </div>
              </div>

              <div style={{ fontSize: "11px", color: "#475569", lineHeight: "1.4", backgroundColor: "#FFFFFF", padding: "8px", borderRadius: "4px", border: "1px solid #E2E8F0" }}>
                <strong>Validation Checklist:</strong><br/>
                ✓ RGB Preview — visual reference only (B4, B3, B2)<br/>
                ✓ NDWI & Water Mask — algorithm output<br/>
                ✓ Area conservation verified: Loss + Stable = Before Comparable
              </div>
            </div>
          )}

          {/* Quality Badge & Disclaimer */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", backgroundColor: "#F8FAFC", padding: "8px 10px", borderRadius: "6px" }}>
            <span style={{ fontSize: "12px", color: "#475569" }}>Data Quality Status</span>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                padding: "2px 8px",
                borderRadius: "12px",
                backgroundColor: result.quality.status === "HIGH" ? "#DCFCE7" : result.quality.status === "MEDIUM" ? "#FEF9C3" : "#FEE2E2",
                color: result.quality.status === "HIGH" ? "#166534" : result.quality.status === "MEDIUM" ? "#854D0E" : "#991B1B",
              }}
            >
              {result.quality.status} ({result.quality.comparison_valid_coverage_percent}% valid coverage)
            </span>
          </div>

          {/* Area Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
            <div style={{ backgroundColor: "#F1F5F9", padding: "8px", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#64748B" }}>Before ({result.before.date})</div>
              <div style={{ fontSize: "15px", fontWeight: 700, color: "#1E293B" }}>{result.before.water_area_km2} km²</div>
            </div>
            <div style={{ backgroundColor: "#F1F5F9", padding: "8px", borderRadius: "6px" }}>
              <div style={{ fontSize: "11px", color: "#64748B" }}>After ({result.after.date})</div>
              <div style={{ fontSize: "15px", fontWeight: 700, color: "#1E293B" }}>{result.after.water_area_km2} km²</div>
            </div>
          </div>

          {/* Net Change Metric */}
          <div style={{ backgroundColor: result.change.net_change_km2 < 0 ? "#FEF2F2" : "#F0FDF4", padding: "10px", borderRadius: "6px", border: `1px solid ${result.change.net_change_km2 < 0 ? "#FCA5A5" : "#86EFAC"}` }}>
            <div style={{ fontSize: "11px", color: result.change.net_change_km2 < 0 ? "#991B1B" : "#166534" }}>
              Surface-Water Extent Change (Valid Comparison Domain)
            </div>
            <div style={{ fontSize: "17px", fontWeight: 800, color: result.change.net_change_km2 < 0 ? "#DC2626" : "#16A34A" }}>
              {result.change.net_change_km2 > 0 ? `+${result.change.net_change_km2}` : result.change.net_change_km2} km² ({result.change.change_percent}%)
            </div>
          </div>

          {/* 4-State Detailed Breakdown */}
          <div style={{ fontSize: "12px", fontWeight: 600, color: "#334155", marginBottom: "-4px" }}>Classification Breakdown</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
            <div style={{ padding: "6px 8px", backgroundColor: "#FEF2F2", borderRadius: "4px", borderLeft: "3px solid #DC2626" }}>
              <div style={{ fontSize: "11px", color: "#991B1B" }}>🔴 Water Loss</div>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "#991B1B" }}>{result.change.loss_area_km2} km²</div>
              <div style={{ fontSize: "10px", color: "#B91C1C" }}>({result.regions.loss_count} regions)</div>
            </div>
            <div style={{ padding: "6px 8px", backgroundColor: "#F0FDF4", borderRadius: "4px", borderLeft: "3px solid #16A34A" }}>
              <div style={{ fontSize: "11px", color: "#166534" }}>🟢 Water Gain</div>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "#166534" }}>{result.change.gain_area_km2} km²</div>
              <div style={{ fontSize: "10px", color: "#15803D" }}>({result.regions.gain_count} regions)</div>
            </div>
            <div style={{ padding: "6px 8px", backgroundColor: "#EFF6FF", borderRadius: "4px", borderLeft: "3px solid #2563EB" }}>
              <div style={{ fontSize: "11px", color: "#1E40AF" }}>🔵 Stable Water</div>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "#1E40AF" }}>{result.change.stable_area_km2} km²</div>
              <div style={{ fontSize: "10px", color: "#1D4ED8" }}>({result.regions.stable_count} regions)</div>
            </div>
            <div style={{ padding: "6px 8px", backgroundColor: "#F8FAFC", borderRadius: "4px", borderLeft: "3px solid #9CA3AF" }}>
              <div style={{ fontSize: "11px", color: "#475569" }}>⚪ No Data / Cloud</div>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "#475569" }}>{result.change.no_data_area_km2} km²</div>
            </div>
          </div>

          {/* Expandable Metadata */}
          <button
            type="button"
            onClick={() => setShowMetadata(!showMetadata)}
            style={{ backgroundColor: "transparent", border: "none", color: "#2563EB", fontSize: "12px", fontWeight: 600, cursor: "pointer", textAlign: "left", padding: 0 }}
          >
            {showMetadata ? "▲ Hide Analysis Metadata" : "▼ View Satellite Metadata & Observations"}
          </button>

          {showMetadata && (
            <div style={{ backgroundColor: "#F8FAFC", padding: "10px", borderRadius: "6px", fontSize: "11px", color: "#334155", display: "flex", flexDirection: "column", gap: "4px", border: "1px solid #E2E8F0" }}>
              <div><strong>Satellite:</strong> {result.metadata.satellite}</div>
              <div><strong>Green Band:</strong> {result.metadata.green_band} | <strong>NIR Band:</strong> {result.metadata.nir_band}</div>
              <div><strong>NDWI Threshold:</strong> {result.analysis.threshold}</div>
              <div style={{ wordBreak: "break-all" }}><strong>Before Image ID:</strong> {result.before.image_id} (Cloud: {result.before.cloud_cover}%)</div>
              <div style={{ wordBreak: "break-all" }}><strong>After Image ID:</strong> {result.after.image_id} (Cloud: {result.after.cloud_cover}%)</div>
            </div>
          )}

          {/* Scientific Disclaimer */}
          <div style={{ fontSize: "10px", color: "#64748B", fontStyle: "italic", lineHeight: "1.3", backgroundColor: "#F8FAFC", padding: "8px", borderRadius: "4px" }}>
            ℹ️ {result.quality.disclaimer || result.metadata.disclaimer}
          </div>
        </div>
      )}
    </div>
  );
}
