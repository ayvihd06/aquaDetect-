import { useState } from "react";

import { Box } from "@mui/material";

import Navbar from "../components/Navbar";
import MapView from "../components/MapView";

// Valid analysis modes: "district" | "ndwi" | "water-change" | "flood" | "drought"
const DEFAULT_MODE = "district";

function Home() {
  const [analysisMode, setAnalysisMode] = useState(DEFAULT_MODE);

  const [selectedDistrict, setSelectedDistrict] = useState(null);
  const [selectedWaterBody, setSelectedWaterBody] = useState(null);

  return (
    <Box sx={{ width: "100%", height: "100vh", overflow: "hidden" }}>

      {/* =================================================
          TOP NAVBAR — primary feature navigation
          ================================================= */}
      <Navbar
        analysisMode={analysisMode}
        onModeChange={setAnalysisMode}
      />

      {/* =================================================
          MAP + FLOATING PANEL
          ================================================= */}
      <Box
        component="main"
        sx={{
          width: "100%",
          height: "calc(100vh - 56px)",
          marginTop: "56px",
        }}
      >
        <MapView
          analysisMode={analysisMode}
          onModeChange={setAnalysisMode}
          onDistrictSelect={setSelectedDistrict}
          onWaterBodySelect={setSelectedWaterBody}
        />
      </Box>
    </Box>
  );
}

export default Home;