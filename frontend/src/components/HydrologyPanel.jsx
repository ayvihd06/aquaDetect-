import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const DISTRICTS = [
  "Ariyalur", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul",
  "Erode", "Kancheepuram", "Kanniyakumari", "Karur", "Madurai", "Nagapattinam",
  "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Salem",
  "Sivaganga", "Thanjavur", "Theni", "Thiruvallur", "Thoothukudi", "Tiruchirappalli",
  "Tirunelveli", "Tiruvannamalai", "Vellore", "Villupuram", "Virudhunagar",
];

// ============================================================
// SHARED STYLES
// ============================================================

const labelSt = {
  fontSize: "11px",
  color: "#64748B",
  fontWeight: 600,
  marginBottom: "4px",
  textTransform: "uppercase",
  letterSpacing: "0.4px",
};

const inputSt = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: "7px",
  border: "1px solid #CBD5E1",
  fontSize: "13px",
  backgroundColor: "#F8FAFC",
  color: "#1E293B",
  outline: "none",
  marginBottom: "10px",
  boxSizing: "border-box",
};

const btnPrimary = (disabled) => ({
  width: "100%",
  padding: "10px",
  borderRadius: "8px",
  border: "none",
  background: disabled ? "#94A3B8" : "linear-gradient(135deg, #0B3D91, #1565C0)",
  color: "#fff",
  fontWeight: 700,
  fontSize: "13px",
  cursor: disabled ? "not-allowed" : "pointer",
  transition: "all 0.2s",
});

const layerBtn = (active) => ({
  flex: 1,
  padding: "7px 4px",
  borderRadius: "6px",
  border: active ? "2px solid #0B3D91" : "1px solid #CBD5E1",
  background: active ? "#EFF6FF" : "#fff",
  color: active ? "#0B3D91" : "#475569",
  fontSize: "10px",
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.15s",
  textAlign: "center",
});

// ============================================================
// INDICATOR BADGE
// ============================================================

function IndicatorBadge({ level }) {
  const config = {
    HIGH:              { emoji: "🔴", bg: "#FEE2E2", color: "#991B1B", label: "HIGH" },
    MODERATE:          { emoji: "🟠", bg: "#FEF3C7", color: "#92400E", label: "MODERATE" },
    LOW:               { emoji: "🟡", bg: "#FEF9C3", color: "#713F12", label: "LOW" },
    CRITICAL:          { emoji: "🚨", bg: "#FEE2E2", color: "#7F1D1D", label: "CRITICAL" },
    NORMAL:            { emoji: "🟢", bg: "#DCFCE7", color: "#166534", label: "NORMAL" },
    INSUFFICIENT_DATA: { emoji: "⚪", bg: "#F1F5F9", color: "#475569", label: "INSUFFICIENT DATA" },
  };
  const c = config[level] || config.INSUFFICIENT_DATA;
  return (
    <div style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      background: c.bg,
      color: c.color,
      padding: "6px 12px",
      borderRadius: "20px",
      fontWeight: 700,
      fontSize: "13px",
      marginTop: "4px",
    }}>
      {c.emoji} {c.label}
    </div>
  );
}

// ============================================================
// STAT ROW
// ============================================================

function StatRow({ label, value, unit, highlight, unavailable }) {
  return (
    <div style={{ marginBottom: "12px" }}>
      <div style={labelSt}>{label}</div>
      <div style={{
        fontSize: "18px",
        fontWeight: 700,
        color: unavailable ? "#9CA3AF" : highlight ? "#0B3D91" : "#1E293B",
      }}>
        {unavailable ? "—" : value !== null && value !== undefined ? `${value}${unit || ""}` : "—"}
      </div>
    </div>
  );
}

// ============================================================
// EXPANDABLE SECTION
// ============================================================

function Expandable({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderTop: "1px solid #E2E8F0", marginTop: "10px" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          background: "none",
          border: "none",
          padding: "10px 0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          fontSize: "12px",
          fontWeight: 700,
          color: "#475569",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
        }}
      >
        {title}
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div style={{ paddingBottom: "10px", fontSize: "12px", color: "#475569", lineHeight: 1.7 }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ============================================================
// UNAVAILABLE CARD
// ============================================================

function UnavailableCard({ reason }) {
  return (
    <div style={{
      background: "#FFF7ED",
      border: "1px solid #FED7AA",
      borderRadius: "10px",
      padding: "14px",
      marginTop: "12px",
      fontSize: "13px",
      color: "#92400E",
    }}>
      <div style={{ fontWeight: 700, marginBottom: "6px" }}>⚠ Analysis unavailable</div>
      <div style={{ lineHeight: 1.5 }}>{reason || "Insufficient satellite observations for the selected period."}</div>
    </div>
  );
}

// ============================================================
// FLOOD MONITORING PANEL
// ============================================================

function FloodPanel({ selectedDistrictName, onFloodResult, onLayerSelect, activeLayer }) {
  const today = new Date().toISOString().split("T")[0];
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().split("T")[0];
  const sixtyDaysAgo  = new Date(Date.now() - 60 * 86400000).toISOString().split("T")[0];

  const [district,     setDistrict]     = useState(selectedDistrictName || "Madurai");
  const [beforeStart,  setBeforeStart]  = useState(sixtyDaysAgo);
  const [beforeEnd,    setBeforeEnd]    = useState(thirtyDaysAgo);
  const [afterStart,   setAfterStart]   = useState(thirtyDaysAgo);
  const [afterEnd,     setAfterEnd]     = useState(today);
  const [rainWindow,   setRainWindow]   = useState(7);

  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);

  const [showMethodology, setShowMethodology] = useState(false);

  const floodLayers = ["before_sar", "after_sar", "sar_change", "permanent_water", "flood_extent"];

  const handleRun = async () => {
    if (!district) { setError("Please select a district."); return; }
    setLoading(true);
    setError(null);
    setResult(null);
    if (onFloodResult) onFloodResult(null);

    try {
      const resp = await fetch(`${API_BASE}/water/flood-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          district,
          before_start: beforeStart,
          before_end:   beforeEnd,
          after_start:  afterStart,
          after_end:    afterEnd,
          rainfall_window_days: rainWindow,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${resp.status}`);
      }
      const data = await resp.json();
      setResult(data);
      if (onFloodResult) onFloodResult(data);
    } catch (err) {
      setError(err.message || "Flood analysis failed.");
    } finally {
      setLoading(false);
    }
  };

  const rainfallAnomaly = result?.rainfall_anomaly_percent ?? result?.rainfall_rainfall_anomaly_percent;
  const rainfall7d = result?.rainfall_7d ?? result?.["rainfall_7d"];

  return (
    <div>
      {/* Header */}
      <div style={{
        fontSize: "14px", fontWeight: 800, color: "#0B3D91",
        marginBottom: "14px", display: "flex", alignItems: "center", gap: "8px",
      }}>
        🌊 FLOOD MONITORING
      </div>

      {/* District */}
      <div style={labelSt}>District</div>
      <select value={district} onChange={e => setDistrict(e.target.value)} style={inputSt}>
        {DISTRICTS.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      {/* Date Range */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
        <div>
          <div style={labelSt}>Before Start</div>
          <input type="date" value={beforeStart} onChange={e => setBeforeStart(e.target.value)} style={inputSt} />
        </div>
        <div>
          <div style={labelSt}>Before End</div>
          <input type="date" value={beforeEnd} onChange={e => setBeforeEnd(e.target.value)} style={inputSt} />
        </div>
        <div>
          <div style={labelSt}>After Start</div>
          <input type="date" value={afterStart} onChange={e => setAfterStart(e.target.value)} style={inputSt} />
        </div>
        <div>
          <div style={labelSt}>After End</div>
          <input type="date" value={afterEnd} onChange={e => setAfterEnd(e.target.value)} style={inputSt} />
        </div>
      </div>

      {/* Rainfall window */}
      <div style={labelSt}>Rainfall Window</div>
      <select value={rainWindow} onChange={e => setRainWindow(Number(e.target.value))} style={inputSt}>
        {[1, 3, 7, 30].map(d => <option key={d} value={d}>{d}-day</option>)}
      </select>

      <button onClick={handleRun} disabled={loading} style={btnPrimary(loading)}>
        {loading ? "⏳ Analysing Satellite Data..." : "🛰 Run Flood Analysis"}
      </button>

      {loading && (
        <div style={{ fontSize: "12px", color: "#64748B", marginTop: "8px", textAlign: "center" }}>
          Querying Sentinel-1 SAR + CHIRPS rainfall via Earth Engine…
        </div>
      )}

      {error && (
        <div style={{
          background: "#FFF1F2", border: "1px solid #FECDD3", borderRadius: "8px",
          padding: "10px", marginTop: "10px", fontSize: "12px", color: "#9F1239",
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Results */}
      {result && !result.available && (
        <UnavailableCard reason={result.reason} />
      )}

      {result && result.available && (
        <div style={{ marginTop: "14px" }}>
          {/* Indicator */}
          <div style={{ textAlign: "center", marginBottom: "14px" }}>
            <div style={{ fontSize: "11px", color: "#64748B", fontWeight: 600, marginBottom: "4px" }}>
              FLOOD INDICATOR
            </div>
            <IndicatorBadge level={result.flood_indicator} />
          </div>

          {/* Stats grid */}
          <div style={{ background: "#F8FAFC", borderRadius: "10px", padding: "12px", marginBottom: "10px" }}>
            <StatRow label="Potential Flood Area" value={result.potential_flood_area_km2?.toFixed(3)} unit=" km²" highlight />
            <StatRow label="Before Water Area"    value={result.before_water_area_km2?.toFixed(3)} unit=" km²" />
            <StatRow label="After Water Area"     value={result.after_water_area_km2?.toFixed(3)}  unit=" km²" />
            <StatRow label="Permanent Water"      value={result.permanent_water_area_km2?.toFixed(3)} unit=" km²" />
            {result.water_expansion_percent !== null && result.water_expansion_percent !== undefined && (
              <StatRow label="Water Expansion"
                value={result.water_expansion_percent >= 0
                  ? `+${result.water_expansion_percent.toFixed(1)}`
                  : result.water_expansion_percent.toFixed(1)
                }
                unit="%"
              />
            )}
          </div>

          {/* Satellite metadata */}
          <div style={{ background: "#F8FAFC", borderRadius: "10px", padding: "12px", marginBottom: "10px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", marginBottom: "8px", textTransform: "uppercase" }}>
              📡 Satellite Evidence
            </div>
            <div style={{ fontSize: "12px", color: "#334155", lineHeight: 1.8 }}>
              <div><strong>Dataset:</strong> Sentinel-1 GRD</div>
              <div><strong>Polarization:</strong> {result.polarization || "VV"}</div>
              <div><strong>Orbit:</strong> {result.orbit_direction}</div>
              <div><strong>Before:</strong> {result.before_date}</div>
              <div><strong>After:</strong> {result.after_date}</div>
              <div><strong>Temporal Gap:</strong> {result.temporal_gap_days} days</div>
              <div style={{ wordBreak: "break-all", fontSize: "10px", color: "#64748B", marginTop: "4px" }}>
                <div>Before ID: {result.before_scene_id}</div>
                <div>After ID: {result.after_scene_id}</div>
              </div>
            </div>
          </div>

          {/* SAR statistics */}
          {(result.before_mean_vv_db !== null || result.after_mean_vv_db !== null) && (
            <div style={{ background: "#F8FAFC", borderRadius: "10px", padding: "12px", marginBottom: "10px" }}>
              <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", marginBottom: "8px", textTransform: "uppercase" }}>
                📊 SAR Backscatter
              </div>
              <div style={{ fontSize: "12px", color: "#334155", lineHeight: 1.8 }}>
                {result.before_mean_vv_db !== null && <div><strong>Before VV mean:</strong> {result.before_mean_vv_db} dB</div>}
                {result.after_mean_vv_db  !== null && <div><strong>After VV mean:</strong>  {result.after_mean_vv_db} dB</div>}
                {result.mean_vv_change_db !== null && <div><strong>ΔVV:</strong> {result.mean_vv_change_db} dB</div>}
                <div><strong>Water threshold:</strong> {result.sar_threshold_db} dB</div>
              </div>
            </div>
          )}

          {/* Rainfall evidence */}
          {(() => {
            const r7   = result["rainfall_7d"]   ?? result["rainfall_rainfall_7d"];
            const r30  = result["rainfall_30d"]  ?? result["rainfall_rainfall_30d"];
            const hist = result["historical_rainfall_mm"] ?? result["rainfall_historical_rainfall_mm"];
            const anom = result["rainfall_anomaly_percent"] ?? result["rainfall_rainfall_anomaly_percent"];
            if (r7 === null && r30 === null && hist === null) return null;
            return (
              <div style={{ background: "#F0FDF4", borderRadius: "10px", padding: "12px", marginBottom: "10px" }}>
                <div style={{ fontSize: "11px", fontWeight: 700, color: "#166534", marginBottom: "8px", textTransform: "uppercase" }}>
                  🌧 Rainfall Evidence (CHIRPS)
                </div>
                <div style={{ fontSize: "12px", color: "#14532D", lineHeight: 1.8 }}>
                  {r7   !== null && r7   !== undefined && <div><strong>7-day rainfall:</strong> {r7} mm</div>}
                  {r30  !== null && r30  !== undefined && <div><strong>30-day rainfall:</strong> {r30} mm</div>}
                  {hist !== null && hist !== undefined && <div><strong>Historical baseline:</strong> {hist} mm</div>}
                  {anom !== null && anom !== undefined && (
                    <div><strong>Rainfall anomaly:</strong> {anom >= 0 ? "+" : ""}{anom}%</div>
                  )}
                </div>
              </div>
            );
          })()}

          {/* Data quality */}
          {result.data_quality && (
            <div style={{
              background: result.data_quality.status === "HIGH" ? "#F0FDF4"
                : result.data_quality.status === "MEDIUM" ? "#FFFBEB" : "#FFF1F2",
              borderRadius: "10px", padding: "12px", marginBottom: "10px",
              fontSize: "12px", color: "#334155",
            }}>
              <div style={{ fontWeight: 700, marginBottom: "4px" }}>
                Data Quality: {result.data_quality.status}
              </div>
              <div>SAR Coverage: {result.data_quality.sar_aoi_coverage_percent}%</div>
              {result.data_quality.warnings?.length > 0 && (
                <div style={{ marginTop: "6px", color: "#92400E" }}>
                  {result.data_quality.warnings.map((w, i) => (
                    <div key={i}>⚠ {w}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Layer selector */}
          {result.tiles && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ ...labelSt, marginBottom: "6px" }}>Map Layers</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {[
                  { id: "flood_before_sar",    label: "Before SAR",    key: "before_sar"    },
                  { id: "flood_after_sar",     label: "After SAR",     key: "after_sar"     },
                  { id: "flood_sar_change",    label: "SAR Change",    key: "sar_change"    },
                  { id: "flood_perm_water",    label: "Perm. Water",   key: "permanent_water" },
                  { id: "flood_extent",        label: "🟣 Flood Extent", key: "flood_extent"  },
                  { id: "flood_stable_water",  label: "Stable Water",  key: "stable_water"  },
                ].map(({ id, label, key }) => (
                  result.tiles[key] ? (
                    <button
                      key={id}
                      id={id}
                      onClick={() => onLayerSelect && onLayerSelect(id)}
                      style={layerBtn(activeLayer === id)}
                    >
                      {label}
                    </button>
                  ) : null
                ))}
                <button
                  onClick={() => onLayerSelect && onLayerSelect("flood_geojson")}
                  style={layerBtn(activeLayer === "flood_geojson")}
                >
                  GeoJSON
                </button>
              </div>
            </div>
          )}

          {/* Expandable: Methodology */}
          <Expandable title="How was this detected?">
            <div>
              <div style={{ fontWeight: 700, marginBottom: "4px" }}>Algorithm:</div>
              <ol style={{ paddingLeft: "16px", margin: 0 }}>
                <li>Sentinel-1 GRD IW VV scenes searched for before/after periods</li>
                <li>Same orbit direction selected (preferred DESCENDING)</li>
                <li>Water-like pixels: VV {"<"} {result.sar_threshold_db} dB (Twele et al. 2016)</li>
                <li>JRC permanent water excluded (occurrence ≥ 75%)</li>
                <li>NEW FLOOD = after_water AND NOT before_water AND NOT permanent</li>
                <li>Connected-pixel noise filter applied</li>
                <li>Area calculated with ee.Image.pixelArea()</li>
                <li>CHIRPS rainfall anomaly vs 5-year historical baseline</li>
              </ol>
              <div style={{ marginTop: "8px", fontStyle: "italic" }}>
                {result.methodology?.disclaimer}
              </div>
            </div>
          </Expandable>

          {/* Orbit mismatch warning */}
          {result.orbit_mismatch_warning && (
            <div style={{
              background: "#FFF7ED", border: "1px solid #FED7AA", borderRadius: "8px",
              padding: "10px", marginTop: "10px", fontSize: "11px", color: "#92400E",
            }}>
              ⚠ Before/after scenes from different orbit directions. Backscatter differences may not be due to flooding alone.
            </div>
          )}

          {/* Disclaimer */}
          <div style={{
            marginTop: "12px", padding: "10px", borderRadius: "8px",
            background: "#F1F5F9", fontSize: "10px", color: "#64748B", lineHeight: 1.5,
          }}>
            <strong>Note:</strong> AquaDetect indicators are satellite-derived environmental indicators
            for monitoring and decision support. They are not official flood warnings or government declarations.
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// DROUGHT MONITORING PANEL
// ============================================================

function DroughtPanel({ selectedDistrictName, onDroughtResult, onLayerSelect, activeLayer }) {
  const today = new Date().toISOString().split("T")[0];
  const ninetyDaysAgo = new Date(Date.now() - 90 * 86400000).toISOString().split("T")[0];

  const [district,     setDistrict]     = useState(selectedDistrictName || "Madurai");
  const [currentStart, setCurrentStart] = useState(ninetyDaysAgo);
  const [currentEnd,   setCurrentEnd]   = useState(today);
  const [season,       setSeason]       = useState("jun_aug");
  const [yearsBack,    setYearsBack]    = useState(5);

  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);

  const handleRun = async () => {
    if (!district) { setError("Please select a district."); return; }
    setLoading(true);
    setError(null);
    setResult(null);
    if (onDroughtResult) onDroughtResult(null);

    try {
      const resp = await fetch(`${API_BASE}/water/drought-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          district,
          current_start: currentStart,
          current_end:   currentEnd,
          season,
          historical_years_back: yearsBack,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${resp.status}`);
      }
      const data = await resp.json();
      setResult(data);
      if (onDroughtResult) onDroughtResult(data);
    } catch (err) {
      setError(err.message || "Drought analysis failed.");
    } finally {
      setLoading(false);
    }
  };

  const seasonLabels = {
    jun_aug:   "Jun–Aug (SW Monsoon)",
    sep_nov:   "Sep–Nov (NE Monsoon)",
    dec_feb:   "Dec–Feb (Winter)",
    mar_may:   "Mar–May (Summer)",
    full_year: "Full Year",
  };

  return (
    <div>
      {/* Header */}
      <div style={{
        fontSize: "14px", fontWeight: 800, color: "#92400E",
        marginBottom: "14px", display: "flex", alignItems: "center", gap: "8px",
      }}>
        ☀ DROUGHT MONITORING
      </div>

      {/* District */}
      <div style={labelSt}>District</div>
      <select value={district} onChange={e => setDistrict(e.target.value)} style={inputSt}>
        {DISTRICTS.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      {/* Current period */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
        <div>
          <div style={labelSt}>Current Start</div>
          <input type="date" value={currentStart} onChange={e => setCurrentStart(e.target.value)} style={inputSt} />
        </div>
        <div>
          <div style={labelSt}>Current End</div>
          <input type="date" value={currentEnd} onChange={e => setCurrentEnd(e.target.value)} style={inputSt} />
        </div>
      </div>

      {/* Season */}
      <div style={labelSt}>Season / Period Label</div>
      <select value={season} onChange={e => setSeason(e.target.value)} style={inputSt}>
        {Object.entries(seasonLabels).map(([k, v]) => (
          <option key={k} value={k}>{v}</option>
        ))}
      </select>

      {/* Historical years */}
      <div style={labelSt}>Historical Baseline (years)</div>
      <select value={yearsBack} onChange={e => setYearsBack(Number(e.target.value))} style={inputSt}>
        {[3, 4, 5, 7, 10].map(y => <option key={y} value={y}>{y} years</option>)}
      </select>

      <button onClick={handleRun} disabled={loading} style={{ ...btnPrimary(loading), background: loading ? "#94A3B8" : "linear-gradient(135deg, #92400E, #D97706)" }}>
        {loading ? "⏳ Analysing Satellite Data..." : "🌡 Run Drought Analysis"}
      </button>

      {loading && (
        <div style={{ fontSize: "12px", color: "#64748B", marginTop: "8px", textAlign: "center" }}>
          Querying Sentinel-2 + CHIRPS via Earth Engine ({yearsBack} historical years)…
        </div>
      )}

      {error && (
        <div style={{
          background: "#FFF1F2", border: "1px solid #FECDD3", borderRadius: "8px",
          padding: "10px", marginTop: "10px", fontSize: "12px", color: "#9F1239",
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Results */}
      {result && !result.available && (
        <UnavailableCard reason={result.reason} />
      )}

      {result && result.available && (
        <div style={{ marginTop: "14px" }}>
          {/* Indicator */}
          <div style={{ textAlign: "center", marginBottom: "14px" }}>
            <div style={{ fontSize: "11px", color: "#64748B", fontWeight: 600, marginBottom: "4px" }}>
              DROUGHT INDICATOR
            </div>
            <IndicatorBadge level={result.drought_indicator} />
          </div>

          {/* Evidence pillars */}
          <div style={{ background: "#FFFBEB", borderRadius: "10px", padding: "12px", marginBottom: "10px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#78350F", marginBottom: "8px", textTransform: "uppercase" }}>
              📊 Drought Evidence
            </div>

            {/* Water area */}
            {result.water_area_available && (
              <div style={{ marginBottom: "8px" }}>
                <div style={labelSt}>Water Extent Anomaly</div>
                <div style={{ fontSize: "16px", fontWeight: 700, color: "#1E293B" }}>
                  {result.water_area_anomaly_percent !== null
                    ? `${result.water_area_anomaly_percent >= 0 ? "+" : ""}${result.water_area_anomaly_percent?.toFixed(1)}%`
                    : "—"}
                </div>
                <div style={{ fontSize: "11px", color: "#64748B" }}>
                  Current: {result.current_water_km2?.toFixed(3)} km² | Historical: {result.historical_water_km2?.toFixed(3)} km²
                </div>
              </div>
            )}

            {/* NDWI */}
            {result.ndwi_available && (
              <div style={{ marginBottom: "8px" }}>
                <div style={labelSt}>NDWI Anomaly</div>
                <div style={{ fontSize: "16px", fontWeight: 700, color: "#1E293B" }}>
                  {result.ndwi_anomaly !== null && result.ndwi_anomaly !== undefined
                    ? `${result.ndwi_anomaly >= 0 ? "+" : ""}${result.ndwi_anomaly?.toFixed(3)}`
                    : "—"}
                </div>
                <div style={{ fontSize: "11px", color: "#64748B" }}>
                  Current: {result.current_ndwi_mean?.toFixed(4)} | Historical: {result.historical_ndwi_mean?.toFixed(4)}
                </div>
              </div>
            )}

            {/* NDVI */}
            {result.ndvi_available && (
              <div style={{ marginBottom: "8px" }}>
                <div style={labelSt}>NDVI Anomaly (Vegetation Stress)</div>
                <div style={{ fontSize: "16px", fontWeight: 700, color: "#1E293B" }}>
                  {result.ndvi_anomaly_percent !== null && result.ndvi_anomaly_percent !== undefined
                    ? `${result.ndvi_anomaly_percent >= 0 ? "+" : ""}${result.ndvi_anomaly_percent?.toFixed(1)}%`
                    : "—"}
                </div>
                <div style={{ fontSize: "11px", color: "#64748B" }}>
                  Current: {result.current_ndvi_mean?.toFixed(4)} | Historical: {result.historical_ndvi_mean?.toFixed(4)}
                </div>
              </div>
            )}

            {/* Rainfall 30d */}
            {result.rainfall_30d_available && (
              <div style={{ marginBottom: "8px" }}>
                <div style={labelSt}>30-Day Rainfall Anomaly</div>
                <div style={{ fontSize: "16px", fontWeight: 700, color: "#1E293B" }}>
                  {result.rainfall_30d_anomaly_percent !== null && result.rainfall_30d_anomaly_percent !== undefined
                    ? `${result.rainfall_30d_anomaly_percent >= 0 ? "+" : ""}${result.rainfall_30d_anomaly_percent?.toFixed(1)}%`
                    : "—"}
                </div>
                <div style={{ fontSize: "11px", color: "#64748B" }}>
                  Current: {result.rainfall_30d_mm} mm | Historical: {result.rainfall_30d_historical_mm} mm
                </div>
              </div>
            )}

            {/* Rainfall 90d */}
            {result.rainfall_90d_available && (
              <div style={{ marginBottom: "4px" }}>
                <div style={labelSt}>90-Day Rainfall Anomaly</div>
                <div style={{ fontSize: "16px", fontWeight: 700, color: "#1E293B" }}>
                  {result.rainfall_90d_anomaly_percent !== null && result.rainfall_90d_anomaly_percent !== undefined
                    ? `${result.rainfall_90d_anomaly_percent >= 0 ? "+" : ""}${result.rainfall_90d_anomaly_percent?.toFixed(1)}%`
                    : "—"}
                </div>
                <div style={{ fontSize: "11px", color: "#64748B" }}>
                  Current: {result.rainfall_90d_mm} mm | Historical: {result.rainfall_90d_historical_mm} mm
                </div>
              </div>
            )}
          </div>

          {/* Satellite metadata */}
          <div style={{ background: "#F8FAFC", borderRadius: "10px", padding: "12px", marginBottom: "10px" }}>
            <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", marginBottom: "6px", textTransform: "uppercase" }}>
              📡 Satellite Metadata
            </div>
            <div style={{ fontSize: "12px", color: "#334155", lineHeight: 1.8 }}>
              <div><strong>Dataset:</strong> Sentinel-2 + CHIRPS</div>
              <div><strong>Current date:</strong> {result.current_date}</div>
              <div><strong>Historical years:</strong> {result.historical_years_used?.join(", ") || "—"}</div>
              <div><strong>Season:</strong> {seasonLabels[season]}</div>
              {result.current_image_id && (
                <div style={{ fontSize: "10px", color: "#64748B", wordBreak: "break-all" }}>
                  {result.current_image_id}
                </div>
              )}
            </div>
          </div>

          {/* Data quality */}
          {result.data_quality && (
            <div style={{
              background: result.data_quality.status === "HIGH" ? "#F0FDF4"
                : result.data_quality.status === "MEDIUM" ? "#FFFBEB" : "#FFF1F2",
              borderRadius: "10px", padding: "12px", marginBottom: "10px",
              fontSize: "12px", color: "#334155",
            }}>
              <div style={{ fontWeight: 700 }}>
                Data Quality: {result.data_quality.status}
              </div>
              <div>Evidence pillars available: {result.data_quality.available_evidence_pillars?.length} / {result.data_quality.total_evidence_pillars}</div>
              {result.data_quality.warnings?.length > 0 && (
                <div style={{ marginTop: "4px", color: "#92400E" }}>
                  {result.data_quality.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
                </div>
              )}
            </div>
          )}

          {/* Map layer selector */}
          {result.tiles && Object.keys(result.tiles).length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ ...labelSt, marginBottom: "6px" }}>Map Layers</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {[
                  { id: "drought_current_rgb",   label: "Satellite" },
                  { id: "drought_current_ndwi",  label: "NDWI" },
                  { id: "drought_current_ndvi",  label: "NDVI" },
                  { id: "drought_current_water", label: "Water Extent" },
                ].map(({ id, label }) => (
                  result.tiles[id.replace("drought_current_", "current_")] ? (
                    <button
                      key={id}
                      id={id}
                      onClick={() => onLayerSelect && onLayerSelect(id)}
                      style={layerBtn(activeLayer === id)}
                    >
                      {label}
                    </button>
                  ) : null
                ))}
              </div>
            </div>
          )}

          {/* Evidence summary */}
          {result.drought_indicator_detail?.evidence_descriptions?.length > 0 && (
            <Expandable title="Evidence Summary">
              <ul style={{ paddingLeft: "16px", margin: 0 }}>
                {result.drought_indicator_detail.evidence_descriptions.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </Expandable>
          )}

          {/* Methodology */}
          <Expandable title="How was this detected?">
            <div>
              <div style={{ fontWeight: 700, marginBottom: "4px" }}>Drought Evidence Pillars:</div>
              <ol style={{ paddingLeft: "16px", margin: 0 }}>
                <li>Water area anomaly (Sentinel-2 NDWI threshold water extent)</li>
                <li>NDWI anomaly (spectral water index vs historical)</li>
                <li>NDVI anomaly (vegetation stress indicator)</li>
                <li>30-day CHIRPS rainfall anomaly</li>
                <li>90-day CHIRPS rainfall anomaly</li>
              </ol>
              <div style={{ marginTop: "8px" }}>
                Historical baseline uses same calendar window for each year.
                Indicator from documented rules in hydrology_config.py only.
              </div>
              <div style={{ marginTop: "6px", fontStyle: "italic" }}>
                {result.methodology?.disclaimer}
              </div>
            </div>
          </Expandable>

          {/* Disclaimer */}
          <div style={{
            marginTop: "12px", padding: "10px", borderRadius: "8px",
            background: "#F1F5F9", fontSize: "10px", color: "#64748B", lineHeight: 1.5,
          }}>
            <strong>Note:</strong> AquaDetect drought indicators are satellite-derived environmental
            indicators for monitoring and decision support. They do not constitute an official drought
            declaration.
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// MAIN HYDROLOGY PANEL
// ============================================================

export default function HydrologyPanel({
  selectedDistrictName,
  onFloodResult,
  onDroughtResult,
  onLayerSelect,
  activeLayer,
  activeTab, // "flood" | "drought" — controlled by navbar; if omitted, shows internal tabs
}) {
  // If activeTab is provided externally (from separate Flood / Drought nav buttons),
  // we use it directly. Otherwise fall back to internal tab state (legacy / standalone use).
  const [internalTab, setInternalTab] = useState("flood");
  const tab = activeTab || internalTab;

  return (
    <div>
      {/* Show internal tab switcher only when NOT controlled by navbar */}
      {!activeTab && (
        <div style={{
          display: "flex",
          background: "#F1F5F9",
          borderRadius: "10px",
          padding: "4px",
          marginBottom: "16px",
          gap: "4px",
        }}>
          <button
            style={{
              flex: 1,
              padding: "9px 4px",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: 700,
              background: internalTab === "flood" ? "#0B3D91" : "transparent",
              color: internalTab === "flood" ? "#fff" : "#4B5563",
              boxShadow: internalTab === "flood" ? "0 2px 6px rgba(0,0,0,0.18)" : "none",
              transition: "all 0.15s",
            }}
            onClick={() => setInternalTab("flood")}
          >
            🌊 Flood
          </button>
          <button
            style={{
              flex: 1,
              padding: "9px 4px",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: 700,
              background: internalTab === "drought" ? "#92400E" : "transparent",
              color: internalTab === "drought" ? "#fff" : "#4B5563",
              boxShadow: internalTab === "drought" ? "0 2px 6px rgba(0,0,0,0.18)" : "none",
              transition: "all 0.15s",
            }}
            onClick={() => setInternalTab("drought")}
          >
            ☀ Drought
          </button>
        </div>
      )}

      {tab === "flood" && (
        <FloodPanel
          selectedDistrictName={selectedDistrictName}
          onFloodResult={onFloodResult}
          onLayerSelect={onLayerSelect}
          activeLayer={activeLayer}
        />
      )}

      {tab === "drought" && (
        <DroughtPanel
          selectedDistrictName={selectedDistrictName}
          onDroughtResult={onDroughtResult}
          onLayerSelect={onLayerSelect}
          activeLayer={activeLayer}
        />
      )}
    </div>
  );
}
