/**
 * Navbar.jsx — AquaDetect Top Navigation
 *
 * Primary feature navigation. Receives analysisMode and onModeChange
 * from Home so the entire app shares one mode state.
 *
 * Features: District | NDWI | Water Change | Flood | Drought
 */

import { useState } from "react";

const MODES = [
  { id: "district",     label: "District",      icon: "🗺" },
  { id: "ndwi",         label: "NDWI",          icon: "🛰" },
  { id: "water-change", label: "Water Change",  icon: "💧" },
  { id: "flood",        label: "Flood",         icon: "🌊" },
  { id: "drought",      label: "Drought",       icon: "☀" },
  { id: "gis-export",   label: "GIS Export",    icon: "📥" },
];


export default function Navbar({ analysisMode, onModeChange }) {
  const [menuOpen, setMenuOpen] = useState(false);

  const handleSelect = (id) => {
    if (onModeChange) onModeChange(id);
    setMenuOpen(false);
  };

  return (
    <>
      {/* ─────────────────────────────────────────────
          NAVBAR BAR
         ───────────────────────────────────────────── */}
      <header
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 1300,
          height: "56px",
          background: "linear-gradient(90deg, #0B3D91 0%, #1565C0 100%)",
          boxShadow: "0 2px 12px rgba(11,61,145,0.35)",
          display: "flex",
          alignItems: "center",
          padding: "0 20px",
          gap: "0",
        }}
      >
        {/* Brand */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontWeight: 800,
            fontSize: "17px",
            color: "#fff",
            letterSpacing: "-0.3px",
            whiteSpace: "nowrap",
            marginRight: "28px",
            flexShrink: 0,
          }}
        >
          🌊 AquaDetect
        </div>

        {/* Desktop nav buttons — pushed to the right */}
        <nav
          className="aq-desktop-nav"
          style={{
            display: "flex",
            gap: "4px",
            marginLeft: "auto",
            alignItems: "center",
          }}
        >
          {MODES.map(({ id, label, icon }) => {
            const active = analysisMode === id;
            return (
              <button
                key={id}
                id={`nav-${id}`}
                onClick={() => handleSelect(id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                  padding: "6px 14px",
                  borderRadius: "6px",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "13px",
                  fontWeight: active ? 700 : 500,
                  background: active
                    ? "rgba(255,255,255,0.22)"
                    : "transparent",
                  color: active ? "#fff" : "rgba(255,255,255,0.80)",
                  boxShadow: active
                    ? "0 0 0 1.5px rgba(255,255,255,0.45)"
                    : "none",
                  transition: "all 0.15s ease",
                  whiteSpace: "nowrap",
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = "rgba(255,255,255,0.12)";
                    e.currentTarget.style.color = "#fff";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "rgba(255,255,255,0.80)";
                  }
                }}
              >
                <span style={{ fontSize: "14px" }}>{icon}</span>
                {label}
              </button>
            );
          })}
        </nav>

        {/* Mobile hamburger */}
        <button
          className="aq-hamburger"
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="Open menu"
          style={{
            display: "none",
            background: "none",
            border: "none",
            color: "#fff",
            fontSize: "22px",
            cursor: "pointer",
            padding: "4px 8px",
            marginLeft: "auto",
          }}
        >
          {menuOpen ? "✕" : "☰"}
        </button>
      </header>

      {/* ─────────────────────────────────────────────
          MOBILE DROPDOWN MENU
         ───────────────────────────────────────────── */}
      {menuOpen && (
        <div
          style={{
            position: "fixed",
            top: "56px",
            left: 0,
            right: 0,
            zIndex: 1299,
            background: "#0B3D91",
            boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
            padding: "8px 16px 16px",
          }}
        >
          <div
            style={{
              fontSize: "10px",
              fontWeight: 700,
              color: "rgba(255,255,255,0.55)",
              letterSpacing: "1px",
              textTransform: "uppercase",
              padding: "10px 4px 6px",
            }}
          >
            ANALYSIS
          </div>
          {MODES.map(({ id, label, icon }) => {
            const active = analysisMode === id;
            return (
              <button
                key={id}
                onClick={() => handleSelect(id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  width: "100%",
                  padding: "12px 10px",
                  borderRadius: "8px",
                  border: "none",
                  cursor: "pointer",
                  fontSize: "14px",
                  fontWeight: active ? 700 : 500,
                  background: active ? "rgba(255,255,255,0.18)" : "transparent",
                  color: "#fff",
                  textAlign: "left",
                  marginBottom: "2px",
                }}
              >
                <span>{icon}</span> {label}
              </button>
            );
          })}
        </div>
      )}

      {/* Responsive CSS */}
      <style>{`
        @media (max-width: 600px) {
          .aq-desktop-nav { display: none !important; }
          .aq-hamburger   { display: flex !important; }
        }
      `}</style>
    </>
  );
}