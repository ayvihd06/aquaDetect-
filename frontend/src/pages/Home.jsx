import { useState } from "react";

import { Box } from "@mui/material";

import Navbar from "../components/Navbar";
import MapView from "../components/MapView";

function Home() {
  const [selectedDistrict, setSelectedDistrict] =
    useState(null);

  const [selectedWaterBody, setSelectedWaterBody] =
    useState(null);

  return (
    <Box
      sx={{
        width: "100%",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      {/* =================================================
          NAVBAR
          ================================================= */}

      <Navbar />


      {/* =================================================
          MAP
          ================================================= */}

      <Box
        component="main"
        sx={{
          width: "100%",
          height: "calc(100vh - 64px)",
          marginTop: "64px",
        }}
      >
        <MapView
          onDistrictSelect={
            setSelectedDistrict
          }

          onWaterBodySelect={
            setSelectedWaterBody
          }
        />
      </Box>
    </Box>
  );
}

export default Home;