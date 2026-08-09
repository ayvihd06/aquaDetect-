import { useEffect, useRef, useState } from "react";

import {
  MapContainer,
  TileLayer,
  GeoJSON,
  useMap,
} from "react-leaflet";

import area from "@turf/area";
import bbox from "@turf/bbox";

import ImageAnalysisPanel from "./ImageAnalysisPanel";


// =========================================================
// DISTRICT CENTERS
// =========================================================

const DISTRICTS = [
  { name: "Ariyalur", lat: 11.1401, lng: 79.0786 },
  { name: "Chennai", lat: 13.0827, lng: 80.2707 },
  { name: "Coimbatore", lat: 11.0168, lng: 76.9558 },
  { name: "Cuddalore", lat: 11.7480, lng: 79.7714 },
  { name: "Dharmapuri", lat: 12.1211, lng: 78.1582 },
  { name: "Dindigul", lat: 10.3673, lng: 77.9803 },
  { name: "Erode", lat: 11.3410, lng: 77.7172 },
  { name: "Kancheepuram", lat: 12.8342, lng: 79.7036 },
  { name: "Kanniyakumari", lat: 8.0883, lng: 77.5385 },
  { name: "Karur", lat: 10.9601, lng: 78.0766 },
  { name: "Madurai", lat: 9.9252, lng: 78.1198 },
  { name: "Nagapattinam", lat: 10.7672, lng: 79.8449 },
  { name: "Namakkal", lat: 11.2194, lng: 78.1677 },
  { name: "Nilgiris", lat: 11.4064, lng: 76.6932 },
  { name: "Perambalur", lat: 11.2333, lng: 78.8833 },
  { name: "Pudukkottai", lat: 10.3833, lng: 78.8001 },
  { name: "Ramanathapuram", lat: 9.3639, lng: 78.8395 },
  { name: "Salem", lat: 11.6643, lng: 78.1460 },
  { name: "Sivaganga", lat: 9.8433, lng: 78.4809 },
  { name: "Thanjavur", lat: 10.7867, lng: 79.1378 },
  { name: "Theni", lat: 10.0104, lng: 77.4768 },
  { name: "Thiruvallur", lat: 13.1439, lng: 79.9080 },
  { name: "Thoothukudi", lat: 8.7642, lng: 78.1348 },
  { name: "Tiruchirappalli", lat: 10.7905, lng: 78.7047 },
  { name: "Tirunelveli", lat: 8.7139, lng: 77.7567 },
  { name: "Tiruvannamalai", lat: 12.2253, lng: 79.0747 },
  { name: "Vellore", lat: 12.9165, lng: 79.1325 },
  { name: "Villupuram", lat: 11.9401, lng: 79.4861 },
  { name: "Virudhunagar", lat: 9.5851, lng: 77.9579 },
];


// =========================================================
// MAP CENTER
// =========================================================

function MapCenter({ district }) {
  const map = useMap();

  useEffect(() => {
    if (!district) return;

    map.flyTo(
      [district.lat, district.lng],
      10,
      {
        duration: 1,
      }
    );
  }, [district, map]);

  return null;
}


// =========================================================
// MAP FIT BOUNDS (for NDWI results)
// =========================================================

function MapFitBounds({ geojson }) {
  const map = useMap();

  useEffect(() => {
    if (!geojson || !geojson.features || geojson.features.length === 0) return;

    try {
      // Collect all coordinates to compute bounding box
      let minLat = Infinity, maxLat = -Infinity;
      let minLng = Infinity, maxLng = -Infinity;

      const collectCoords = (coords) => {
        if (!Array.isArray(coords)) return;
        if (typeof coords[0] === "number") {
          // [lng, lat]
          const [lng, lat] = coords;
          if (lat < minLat) minLat = lat;
          if (lat > maxLat) maxLat = lat;
          if (lng < minLng) minLng = lng;
          if (lng > maxLng) maxLng = lng;
        } else {
          coords.forEach(collectCoords);
        }
      };

      geojson.features.forEach((f) => {
        if (f.geometry && f.geometry.coordinates) {
          collectCoords(f.geometry.coordinates);
        }
      });

      if (
        isFinite(minLat) && isFinite(maxLat) &&
        isFinite(minLng) && isFinite(maxLng)
      ) {
        map.fitBounds(
          [[minLat, minLng], [maxLat, maxLng]],
          { padding: [30, 30], maxZoom: 14 }
        );
      }
    } catch (err) {
      console.warn("MapFitBounds error:", err);
    }
  }, [geojson, map]);

  return null;
}


// =========================================================
// MAP VIEW
// =========================================================

function MapView({
  onDistrictSelect,
  onWaterBodySelect,
}) {
  const [selectedDistrict, setSelectedDistrict] =
    useState(null);

  const [geojson, setGeojson] =
    useState(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState(null);

  const [hoveredWaterBody, setHoveredWaterBody] =
    useState(null);


  // =======================================================
  // ANALYSIS MODE
  // =======================================================

  const [analysisMode, setAnalysisMode] =
    useState("district"); // "district" | "image"


  // =======================================================
  // NDWI STATE
  // =======================================================

  const [ndwiGeojson, setNdwiGeojson] =
    useState(null);

  const [ndwiStats, setNdwiStats] =
    useState(null);

  // Key to force GeoJSON layer remount when ndwiGeojson changes
  const ndwiKeyRef = useRef(0);


  const [districtStats, setDistrictStats] =
    useState({
      totalWaterAreaKm2: 0,
      waterBodyCount: 0,
      boundingBoxCount: 0,
    });


  // =======================================================
  // SELECTED WATER BODY
  // =======================================================

  const [selectedWaterBody, setLocalSelectedWaterBody] =
    useState(null);


  // =======================================================
  // WATER STYLE
  // =======================================================

  const waterStyle = {
    color: "#0B3D91",
    fillColor: "#1565C0",
    fillOpacity: 0.55,
    weight: 1.5,
  };


  // =======================================================
  // HOVER STYLE
  // =======================================================

  const hoverStyle = {
    color: "#062B63",
    fillColor: "#0D47A1",
    fillOpacity: 0.75,
    weight: 3,
  };


  // =======================================================
  // LOAD GEOJSON
  // =======================================================

  useEffect(() => {
    if (!selectedDistrict) {
      setGeojson(null);

      setDistrictStats({
        totalWaterAreaKm2: 0,
        waterBodyCount: 0,
        boundingBoxCount: 0,
      });

      setLocalSelectedWaterBody(null);

      if (onWaterBodySelect) {
        onWaterBodySelect(null);
      }

      return;
    }


    const loadGeoJSON = async () => {
      setLoading(true);
      setError(null);
      setGeojson(null);
      setHoveredWaterBody(null);
      setLocalSelectedWaterBody(null);

      if (onWaterBodySelect) {
        onWaterBodySelect(null);
      }


      try {
        const districtFolder =
          selectedDistrict.name.toLowerCase();

        const url =
          `/data/${districtFolder}/water_polygons.geojson`;

        console.log(
          "Loading GeoJSON:",
          url
        );


        const response =
          await fetch(url);


        if (!response.ok) {
          throw new Error(
            `Could not load ${selectedDistrict.name} GeoJSON`
          );
        }


        const data =
          await response.json();


        setGeojson(data);


        // =================================================
        // CALCULATE DISTRICT STATISTICS
        // =================================================

        const features =
          data?.features || [];


        let totalArea = 0;

        let validBoundingBoxes = 0;


        features.forEach(
          (feature) => {
            try {
              totalArea +=
                area(feature);

              const featureBox =
                bbox(feature);

              if (
                featureBox &&
                featureBox.length === 4
              ) {
                validBoundingBoxes += 1;
              }
            } catch (err) {
              console.warn(
                "Could not calculate feature statistics:",
                err
              );
            }
          }
        );


        setDistrictStats({
          totalWaterAreaKm2:
            totalArea / 1000000,

          waterBodyCount:
            features.length,

          boundingBoxCount:
            validBoundingBoxes,
        });


        console.log(
          "District statistics:",
          {
            totalWaterAreaKm2:
              totalArea / 1000000,

            waterBodyCount:
              features.length,

            boundingBoxCount:
              validBoundingBoxes,
          }
        );


        console.log(
          `${selectedDistrict.name} GeoJSON loaded`
        );

      } catch (err) {
        console.error(
          "GeoJSON loading error:",
          err
        );

        setError(
          err.message ||
          "Unable to load district data."
        );

      } finally {
        setLoading(false);
      }
    };


    loadGeoJSON();

  }, [
    selectedDistrict,
    onWaterBodySelect,
  ]);


  // =======================================================
  // DISTRICT CHANGE
  // =======================================================

  const handleDistrictChange = (
    event
  ) => {
    const district =
      DISTRICTS.find(
        (item) =>
          item.name ===
          event.target.value
      ) || null;


    console.log(
      "Selected district:",
      district
    );


    setSelectedDistrict(
      district
    );


    if (onDistrictSelect) {
      onDistrictSelect(
        district
      );
    }
  };


  // =======================================================
  // CREATE HOVER INFORMATION
  // =======================================================

  const createHoverInfo = (
    feature,
    isNdwi = false
  ) => {
    try {
      const areaSquareMeters =
        area(feature);

      const areaKm2 =
        areaSquareMeters /
        1000000;


      const boundingBox =
        bbox(feature);


      const west =
        boundingBox[0];

      const south =
        boundingBox[1];

      const east =
        boundingBox[2];

      const north =
        boundingBox[3];


      const longitude =
        (west + east) / 2;

      const latitude =
        (south + north) / 2;


      // Use backend-computed centroid for NDWI features
      // (more accurate than bounding-box midpoint for irregular shapes)
      const finalLat = isNdwi && feature?.properties?.centroid_lat
        ? feature.properties.centroid_lat
        : latitude;

      const finalLng = isNdwi && feature?.properties?.centroid_lon
        ? feature.properties.centroid_lon
        : longitude;

      return {
        areaKm2,
        latitude:  finalLat,
        longitude: finalLng,
        ndwiMean:  isNdwi
          ? (feature?.properties?.ndwi_mean ?? null)
          : null,
      };

    } catch (err) {
      console.error(
        "Hover information error:",
        err
      );

      return null;
    }
  };


  // =======================================================
  // WATER POLYGON EVENTS  (district polygons)
  // =======================================================

  const onEachWaterBody = (
    feature,
    layer
  ) => {

    layer.on({

      // ===================================================
      // HOVER
      // ===================================================

      mouseover: () => {
        const hoverInfo =
          createHoverInfo(
            feature
          );


        if (hoverInfo) {
          setHoveredWaterBody(
            hoverInfo
          );
        }


        layer.setStyle(
          hoverStyle
        );


        if (
          layer.bringToFront
        ) {
          layer.bringToFront();
        }
      },


      // ===================================================
      // MOUSE OUT
      // ===================================================

      mouseout: () => {
        setHoveredWaterBody(
          null
        );

        layer.setStyle(
          waterStyle
        );
      },


      // ===================================================
      // CLICK
      // ===================================================

      click: async () => {

        console.log(
          "Water polygon clicked:",
          feature
        );


        try {

          // -----------------------------------------------
          // AREA
          // -----------------------------------------------

          const areaSquareMeters =
            area(feature);

          const areaKm2 =
            areaSquareMeters /
            1000000;


          // -----------------------------------------------
          // BOUNDING BOX
          // -----------------------------------------------

          const boundingBox =
            bbox(feature);


          const west =
            boundingBox[0];

          const south =
            boundingBox[1];

          const east =
            boundingBox[2];

          const north =
            boundingBox[3];


          // -----------------------------------------------
          // CENTER
          // -----------------------------------------------

          const centerLongitude =
            (west + east) / 2;

          const centerLatitude =
            (south + north) / 2;


          // -----------------------------------------------
          // SELECTED WATER BODY
          // -----------------------------------------------

          const selected = {
            feature,

            geometryType:
              feature?.geometry?.type ||
              "Unknown",

            areaKm2:
              Number(
                areaKm2.toFixed(4)
              ),

            boundingBox: {
              west:
                Number(
                  west.toFixed(6)
                ),

              south:
                Number(
                  south.toFixed(6)
                ),

              east:
                Number(
                  east.toFixed(6)
                ),

              north:
                Number(
                  north.toFixed(6)
                ),
            },

            center: {
              latitude:
                Number(
                  centerLatitude.toFixed(6)
                ),

              longitude:
                Number(
                  centerLongitude.toFixed(6)
                ),
            },

            properties:
              feature?.properties || {},

            osm: {
              loading: true,
              found: false,
              name: null,
            },
          };


          // -----------------------------------------------
          // SHOW IMMEDIATELY
          // -----------------------------------------------

          setLocalSelectedWaterBody(
            selected
          );


          if (onWaterBodySelect) {
            onWaterBodySelect(
              selected
            );
          }


          // -----------------------------------------------
          // OSM LOOKUP
          // -----------------------------------------------

          console.log(
            "Searching OpenStreetMap:",
            centerLatitude,
            centerLongitude
          );


          const response =
            await fetch(
              "http://127.0.0.1:8000/osm/water-name",
              {
                method: "POST",

                headers: {
                  "Content-Type":
                    "application/json",
                },

                body: JSON.stringify({
                  latitude:
                    centerLatitude,

                  longitude:
                    centerLongitude,
                }),
              }
            );


          if (!response.ok) {
            throw new Error(
              `OSM request failed: ${response.status}`
            );
          }


          const osmData =
            await response.json();


          console.log(
            "OSM response:",
            osmData
          );


          // -----------------------------------------------
          // UPDATE SELECTED WATER BODY
          // -----------------------------------------------

          const updatedWaterBody = {
            ...selected,

            osm: {
              loading: false,

              found:
                osmData.found === true,

              name:
                osmData.name ||
                null,

              source:
                osmData.found === true
                  ? "OpenStreetMap"
                  : "No OSM name found",

              distanceKm:
                osmData.distance_km ??
                null,

              osmType:
                osmData.osm_type ??
                null,

              osmId:
                osmData.osm_id ??
                null,
            },
          };


          setLocalSelectedWaterBody(
            updatedWaterBody
          );


          if (onWaterBodySelect) {
            onWaterBodySelect(
              updatedWaterBody
            );
          }

        } catch (err) {

          console.error(
            "Water body / OSM lookup error:",
            err
          );


          const failedWaterBody = {
            feature,

            geometryType:
              feature?.geometry?.type ||
              "Unknown",

            areaKm2:
              Number(
                (
                  area(feature) /
                  1000000
                ).toFixed(4)
              ),

            boundingBox: {
              west:
                Number(
                  bbox(feature)[0]
                    .toFixed(6)
                ),

              south:
                Number(
                  bbox(feature)[1]
                    .toFixed(6)
                ),

              east:
                Number(
                  bbox(feature)[2]
                    .toFixed(6)
                ),

              north:
                Number(
                  bbox(feature)[3]
                    .toFixed(6)
                ),
            },

            center: {
              latitude:
                Number(
                  (
                    (
                      bbox(feature)[1] +
                      bbox(feature)[3]
                    ) / 2
                  ).toFixed(6)
                ),

              longitude:
                Number(
                  (
                    (
                      bbox(feature)[0] +
                      bbox(feature)[2]
                    ) / 2
                  ).toFixed(6)
                ),
            },

            properties:
              feature?.properties || {},

            osm: {
              loading: false,
              found: false,
              name: null,
              source:
                "OSM lookup failed",
            },
          };


          setLocalSelectedWaterBody(
            failedWaterBody
          );


          if (onWaterBodySelect) {
            onWaterBodySelect(
              failedWaterBody
            );
          }
        }
      },
    });
  };


  // =======================================================
  // NDWI POLYGON EVENTS
  // =======================================================
  //
  // Same pattern as district polygons:
  //   hover → local data only (NO OSM)
  //   click → POST /osm/water-name (same as district)
  // =======================================================

  const onEachNdwiBody = (
    feature,
    layer
  ) => {

    layer.on({

      // =================================================
      // HOVER (NDWI)
      // =================================================

      mouseover: () => {
        const hoverInfo = createHoverInfo(feature, true);

        if (hoverInfo) {
          setHoveredWaterBody(hoverInfo);
        }

        layer.setStyle(hoverStyle);

        if (layer.bringToFront) {
          layer.bringToFront();
        }
      },


      // =================================================
      // MOUSE OUT (NDWI)
      // =================================================

      mouseout: () => {
        setHoveredWaterBody(null);
        layer.setStyle(waterStyle);
      },


      // =================================================
      // CLICK (NDWI)  — same OSM lookup as district
      // =================================================

      click: async () => {

        console.log(
          "NDWI polygon clicked:",
          feature
        );


        try {

          const areaSquareMeters = area(feature);
          const areaKm2 = areaSquareMeters / 1000000;

          const boundingBox = bbox(feature);
          const west  = boundingBox[0];
          const south = boundingBox[1];
          const east  = boundingBox[2];
          const north = boundingBox[3];

          // Prefer backend centroid from properties
          const centerLatitude = feature?.properties?.centroid_lat
            ?? (south + north) / 2;
          const centerLongitude = feature?.properties?.centroid_lon
            ?? (west + east) / 2;


          // -----------------------------------------------
          // SELECTED WATER BODY  (NDWI)
          // -----------------------------------------------

          const selected = {
            feature,

            geometryType:
              feature?.geometry?.type || "Unknown",

            areaKm2: Number(areaKm2.toFixed(4)),

            detectionMethod: "NDWI",

            ndwiMean: feature?.properties?.ndwi_mean ?? null,

            ndwiThreshold: feature?.properties?.ndwi_threshold ?? null,

            boundingBox: {
              west:  Number(west.toFixed(6)),
              south: Number(south.toFixed(6)),
              east:  Number(east.toFixed(6)),
              north: Number(north.toFixed(6)),
            },

            center: {
              latitude:  Number(centerLatitude.toFixed(6)),
              longitude: Number(centerLongitude.toFixed(6)),
            },

            properties: feature?.properties || {},

            osm: {
              loading: true,
              found:   false,
              name:    null,
            },
          };


          // -----------------------------------------------
          // SHOW IMMEDIATELY
          // -----------------------------------------------

          setLocalSelectedWaterBody(selected);

          if (onWaterBodySelect) {
            onWaterBodySelect(selected);
          }


          // -----------------------------------------------
          // OSM LOOKUP (existing endpoint — reused)
          // -----------------------------------------------

          console.log(
            "[NDWI] Searching OpenStreetMap:",
            centerLatitude,
            centerLongitude
          );


          const response = await fetch(
            "http://127.0.0.1:8000/osm/water-name",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                latitude:  centerLatitude,
                longitude: centerLongitude,
              }),
            }
          );


          if (!response.ok) {
            throw new Error(
              `OSM request failed: ${response.status}`
            );
          }


          const osmData = await response.json();

          console.log("[NDWI] OSM response:", osmData);


          // -----------------------------------------------
          // UPDATE SELECTED WATER BODY
          // -----------------------------------------------

          const updatedWaterBody = {
            ...selected,
            osm: {
              loading: false,
              found:   osmData.found === true,
              name:    osmData.name || null,

              // NDWI detection is valid even without OSM name
              source: osmData.found === true
                ? "OpenStreetMap"
                : "NDWI detection",

              distanceKm: osmData.distance_km ?? null,
              osmType:    osmData.osm_type    ?? null,
              osmId:      osmData.osm_id      ?? null,
            },
          };


          setLocalSelectedWaterBody(updatedWaterBody);

          if (onWaterBodySelect) {
            onWaterBodySelect(updatedWaterBody);
          }


        } catch (err) {

          console.error(
            "[NDWI] Water body / OSM lookup error:",
            err
          );


          // NDWI polygon is still valid — show it without name
          const failedWaterBody = {
            feature,
            geometryType: feature?.geometry?.type || "Unknown",
            areaKm2: Number(
              (area(feature) / 1000000).toFixed(4)
            ),
            detectionMethod: "NDWI",
            ndwiMean:      feature?.properties?.ndwi_mean ?? null,
            ndwiThreshold: feature?.properties?.ndwi_threshold ?? null,
            boundingBox: {
              west:  Number(bbox(feature)[0].toFixed(6)),
              south: Number(bbox(feature)[1].toFixed(6)),
              east:  Number(bbox(feature)[2].toFixed(6)),
              north: Number(bbox(feature)[3].toFixed(6)),
            },
            center: {
              latitude: Number(
                (feature?.properties?.centroid_lat ??
                  ((bbox(feature)[1] + bbox(feature)[3]) / 2)
                ).toFixed(6)
              ),
              longitude: Number(
                (feature?.properties?.centroid_lon ??
                  ((bbox(feature)[0] + bbox(feature)[2]) / 2)
                ).toFixed(6)
              ),
            },
            properties: feature?.properties || {},
            osm: {
              loading: false,
              found:   false,
              name:    null,
              source:  "NDWI detection",
            },
          };


          setLocalSelectedWaterBody(failedWaterBody);

          if (onWaterBodySelect) {
            onWaterBodySelect(failedWaterBody);
          }
        }
      },
    });
  };


  // =======================================================
  // NDWI RESULT HANDLER
  // =======================================================

  const handleNdwiResult = (geojson, stats) => {
    ndwiKeyRef.current += 1;
    setNdwiGeojson(geojson);
    setNdwiStats(stats);
    setLocalSelectedWaterBody(null);
    if (onWaterBodySelect) onWaterBodySelect(null);
  };


  // =======================================================
  // MODE SWITCH HANDLER
  // =======================================================

  const handleModeSwitch = (mode) => {
    setAnalysisMode(mode);
    setLocalSelectedWaterBody(null);
    setHoveredWaterBody(null);
    if (onWaterBodySelect) onWaterBodySelect(null);

    if (mode === "district") {
      // Clear NDWI layer when switching to district mode
      setNdwiGeojson(null);
      setNdwiStats(null);
    } else {
      // Clear district layer when switching to image mode
      setGeojson(null);
      setSelectedDistrict(null);
      setDistrictStats({
        totalWaterAreaKm2: 0,
        waterBodyCount:    0,
        boundingBoxCount:  0,
      });
    }
  };


  // =======================================================
  // RENDER
  // =======================================================

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
      }}
    >

      {/* =================================================
          MAIN INFORMATION PANEL
          ================================================= */}

      <div
        style={{
          position: "absolute",

          top: "20px",
          left: "20px",

          zIndex: 1000,

          width: "320px",

          maxHeight:
            "calc(100vh - 105px)",

          overflowY: "auto",

          background:
            "#ffffff",

          borderRadius: "16px",

          boxShadow:
            "0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.04)",

          padding: "20px",

          boxSizing: "border-box",
        }}
      >

        {/* ===============================================
            MODE TOGGLE
            =============================================== */}

        <div
          style={{
            fontSize: "11px",
            fontWeight: 700,
            color: "#6b7280",
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            marginBottom: "10px",
          }}
        >
          ANALYSIS MODE
        </div>

        <div
          style={{
            display: "flex",
            marginBottom: "20px",
            background: "#f1f5f9",
            borderRadius: "8px",
            padding: "4px",
          }}
        >
          {["district", "image"].map((mode) => (
            <button
              key={mode}
              onClick={() => handleModeSwitch(mode)}
              style={{
                flex: 1,
                padding: "8px 12px",
                borderRadius: "6px",
                border: "none",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: 600,
                background: analysisMode === mode
                  ? "#0b409c"
                  : "transparent",
                color: analysisMode === mode
                  ? "#ffffff"
                  : "#4b5563",
                boxShadow: analysisMode === mode
                  ? "0 2px 4px rgba(11, 64, 156, 0.25)"
                  : "none",
                transition: "all 0.15s ease",
              }}
            >
              {mode === "district" ? "District Analysis" : "Image Analysis"}
            </button>
          ))}
        </div>


        {/* ===============================================
            DISTRICT MODE CONTROLS
            =============================================== */}

        {analysisMode === "district" && (
          <>

        {/* ===============================================
            SELECT DISTRICT
            =============================================== */}

        <div
          style={{
            fontSize: "16px",
            fontWeight: 700,
            color: "#111827",
            marginBottom: "12px",
          }}
        >
          Select District
        </div>


        <select
          value={
            selectedDistrict?.name || ""
          }

          onChange={
            handleDistrictChange
          }

          style={{
            width: "100%",
            padding: "10px 12px",

            borderRadius: "8px",

            border:
              "1px solid #e5e7eb",

            fontSize: "14px",

            color: "#1f2937",

            background: "#ffffff",

            boxSizing: "border-box",

            outline: "none",

            boxShadow: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
          }}
        >

          <option value="">
            Select a district
          </option>

          {DISTRICTS.map(
            (district) => (
              <option
                key={district.name}
                value={district.name}
              >
                {district.name}
              </option>
            )
          )}

        </select>


        {/* ===============================================
            BEFORE DISTRICT SELECTION
            =============================================== */}

        {!selectedDistrict && (

          <div
            style={{
              marginTop: "16px",

              fontSize: "13px",

              color: "#9ca3af",

              lineHeight: 1.5,
            }}
          >
            Select a district to view water analysis.
          </div>

        )}


        {/* ===============================================
            LOADING
            =============================================== */}

        {loading && (

          <div
            style={{
              marginTop: "18px",

              fontSize: "13px",

              color: "#555",
            }}
          >
            Loading water data...
          </div>

        )}


        {/* ===============================================
            ERROR
            =============================================== */}

        {error && (

          <div
            style={{
              marginTop: "18px",

              padding: "10px",

              borderRadius: "7px",

              background: "#fff1f1",

              color: "#b00020",

              fontSize: "13px",
            }}
          >
            {error}
          </div>

        )}


        {/* ===============================================
            DISTRICT INFORMATION
            =============================================== */}

        {selectedDistrict &&
          !loading &&
          !error && (

            <>

              <div
                style={{
                  marginTop: "18px",

                  paddingTop: "16px",

                  borderTop:
                    "1px solid #e5e5e5",
                }}
              >

                <div
                  style={{
                    fontSize: "18px",

                    fontWeight: 700,

                    color: "#0B3D91",

                    marginBottom: "3px",
                  }}
                >
                  {selectedDistrict.name}
                </div>


                <div
                  style={{
                    fontSize: "13px",

                    color: "#3c8c3c",

                    marginBottom: "20px",
                  }}
                >
                  ✓ Water polygons loaded
                </div>


                {/* =====================================
                    TOTAL WATER AREA
                    ===================================== */}

                <div
                  style={{
                    marginBottom: "18px",
                  }}
                >

                  <div
                    style={{
                      fontSize: "13px",

                      color: "#555",

                      marginBottom: "4px",
                    }}
                  >
                    Total Water Area
                  </div>

                  <div
                    style={{
                      fontSize: "21px",

                      fontWeight: 700,

                      color: "#111",
                    }}
                  >
                    {districtStats.totalWaterAreaKm2.toFixed(
                      2
                    )}{" "}
                    km²
                  </div>

                </div>


                {/* =====================================
                    WATER BODY COUNT
                    ===================================== */}

                <div
                  style={{
                    marginBottom: "18px",
                  }}
                >

                  <div
                    style={{
                      fontSize: "13px",

                      color: "#555",

                      marginBottom: "4px",
                    }}
                  >
                    Distinct Water Bodies
                  </div>

                  <div
                    style={{
                      fontSize: "21px",

                      fontWeight: 700,

                      color: "#111",
                    }}
                  >
                    {districtStats.waterBodyCount}
                  </div>

                </div>


                {/* =====================================
                    BOUNDING BOX COUNT
                    ===================================== */}

                <div
                  style={{
                    marginBottom: "4px",
                  }}
                >

                  <div
                    style={{
                      fontSize: "13px",

                      color: "#555",

                      marginBottom: "4px",
                    }}
                  >
                    Bounding Boxes
                  </div>

                  <div
                    style={{
                      fontSize: "21px",

                      fontWeight: 700,

                      color: "#111",
                    }}
                  >
                    {districtStats.boundingBoxCount}
                  </div>

                </div>

              </div>


              {/* =========================================
                  SELECTED WATER BODY
                  ========================================= */}

              {selectedWaterBody && (

                <div
                  style={{
                    marginTop: "20px",

                    paddingTop: "18px",

                    borderTop:
                      "1px solid #e5e5e5",
                  }}
                >

                  <div
                    style={{
                      fontSize: "16px",

                      fontWeight: 700,

                      marginBottom: "20px",
                    }}
                  >
                    Selected Water Body
                  </div>


                  {/* NAME */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    Name
                  </div>

                  <div
                    style={{
                      fontSize: "16px",
                      fontWeight: 600,
                      marginBottom: "17px",
                    }}
                  >
                    {selectedWaterBody.osm?.loading
                      ? "Looking up..."
                      : selectedWaterBody.osm?.found
                        ? selectedWaterBody.osm.name
                        : "Unnamed water body"}
                  </div>


                  {/* SOURCE */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    Source
                  </div>

                  <div
                    style={{
                      fontSize: "14px",
                      marginBottom: "17px",
                    }}
                  >
                    {selectedWaterBody.osm?.loading
                      ? "OpenStreetMap lookup..."
                      : selectedWaterBody.osm?.found
                        ? "OpenStreetMap"
                        : selectedWaterBody.osm?.source ||
                          "No OSM name found"}
                  </div>


                  {/* AREA */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    Area
                  </div>

                  <div
                    style={{
                      fontSize: "14px",
                      marginBottom: "17px",
                    }}
                  >
                    {selectedWaterBody.areaKm2.toFixed(
                      4
                    )}{" "}
                    km²
                  </div>


                  {/* LATITUDE */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    Latitude
                  </div>

                  <div
                    style={{
                      fontSize: "14px",
                      marginBottom: "17px",
                    }}
                  >
                    {selectedWaterBody.center.latitude.toFixed(
                      6
                    )}
                  </div>


                  {/* LONGITUDE */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    Longitude
                  </div>

                  <div
                    style={{
                      fontSize: "14px",
                      marginBottom: "17px",
                    }}
                  >
                    {selectedWaterBody.center.longitude.toFixed(
                      6
                    )}
                  </div>


                  {/* GEOMETRY */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "4px",
                    }}
                  >
                    Geometry
                  </div>

                  <div
                    style={{
                      fontSize: "14px",
                      marginBottom: "17px",
                    }}
                  >
                    {selectedWaterBody.geometryType}
                  </div>


                  {/* BOUNDING BOX */}

                  <div
                    style={{
                      fontSize: "12px",
                      color: "#666",
                      marginBottom: "6px",
                    }}
                  >
                    Bounding Box
                  </div>

                  <div
                    style={{
                      fontSize: "13px",
                      lineHeight: 1.7,
                    }}
                  >

                    <div>
                      West:{" "}
                      {selectedWaterBody.boundingBox.west}
                    </div>

                    <div>
                      South:{" "}
                      {selectedWaterBody.boundingBox.south}
                    </div>

                    <div>
                      East:{" "}
                      {selectedWaterBody.boundingBox.east}
                    </div>

                    <div>
                      North:{" "}
                      {selectedWaterBody.boundingBox.north}
                    </div>

                  </div>

                </div>

              )}

            </>

          )}

            </>

          )}


        {/* ===============================================
            IMAGE ANALYSIS PANEL
            =============================================== */}

        {analysisMode === "image" && (

          <ImageAnalysisPanel
            onNdwiResult={handleNdwiResult}
          />

        )}


        {/* ===============================================
            NDWI SELECTED WATER BODY (image mode)
            =============================================== */}

        {analysisMode === "image" &&
          selectedWaterBody && (

          <div
            style={{
              marginTop: "16px",
              paddingTop: "16px",
              borderTop: "1px solid #e5e5e5",
            }}
          >

            <div
              style={{
                fontSize: "15px",
                fontWeight: 700,
                marginBottom: "14px",
              }}
            >
              Selected Water Body
            </div>


            {/* NAME */}
            <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>Name</div>
            <div style={{ fontSize: "15px", fontWeight: 600, marginBottom: "13px" }}>
              {selectedWaterBody.osm?.loading
                ? "Looking up…"
                : selectedWaterBody.osm?.found
                  ? selectedWaterBody.osm.name
                  : "Unnamed water body"}
            </div>

            {/* DETECTION METHOD */}
            <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>Detection Method</div>
            <div style={{ fontSize: "13px", marginBottom: "13px" }}>
              {selectedWaterBody.detectionMethod || "NDWI"}
            </div>

            {/* SOURCE */}
            <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>Source</div>
            <div style={{ fontSize: "13px", marginBottom: "13px" }}>
              {selectedWaterBody.osm?.loading
                ? "OpenStreetMap lookup…"
                : selectedWaterBody.osm?.found
                  ? "OpenStreetMap"
                  : selectedWaterBody.osm?.source || "NDWI detection"}
            </div>

            {/* AREA */}
            <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>Area</div>
            <div style={{ fontSize: "13px", marginBottom: "13px" }}>
              {selectedWaterBody.areaKm2?.toFixed(4)} km²
            </div>

            {/* LATITUDE */}
            <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>Latitude</div>
            <div style={{ fontSize: "13px", marginBottom: "13px" }}>
              {selectedWaterBody.center?.latitude?.toFixed(6)}
            </div>

            {/* LONGITUDE */}
            <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>Longitude</div>
            <div style={{ fontSize: "13px", marginBottom: "13px" }}>
              {selectedWaterBody.center?.longitude?.toFixed(6)}
            </div>

            {/* NDWI MEAN */}
            {selectedWaterBody.ndwiMean !== null &&
              selectedWaterBody.ndwiMean !== undefined && (
              <>
                <div style={{ fontSize: "12px", color: "#666", marginBottom: "3px" }}>NDWI (mean)</div>
                <div style={{ fontSize: "13px", marginBottom: "13px" }}>
                  {Number(selectedWaterBody.ndwiMean).toFixed(4)}
                </div>
              </>
            )}

          </div>

        )}

      </div>


      {/* =================================================
          HOVER CARD
          ================================================= */}

      {hoveredWaterBody && (

        <div
          style={{
            position: "absolute",

            top: "20px",

            right: "20px",

            zIndex: 1000,

            width: "250px",

            background:
              "rgba(255,255,255,0.97)",

            padding: "16px 18px",

            borderRadius: "12px",

            boxShadow:
              "0 4px 18px rgba(0,0,0,0.20)",

            pointerEvents: "none",
          }}
        >

          <div
            style={{
              fontSize: "16px",

              fontWeight: 700,

              color: "#0B3D91",

              marginBottom: "12px",
            }}
          >
            Water Body
          </div>


          <div
            style={{
              fontSize: "13px",
              marginBottom: "8px",
            }}
          >
            <strong>
              Area:
            </strong>{" "}
            {hoveredWaterBody.areaKm2.toFixed(
              4
            )}{" "}
            km²
          </div>


          <div
            style={{
              fontSize: "13px",
              marginBottom: "8px",
            }}
          >
            <strong>
              Latitude:
            </strong>{" "}
            {hoveredWaterBody.latitude.toFixed(
              6
            )}
          </div>


          <div
            style={{
              fontSize: "13px",
            }}
          >
            <strong>
              Longitude:
            </strong>{" "}
            {hoveredWaterBody.longitude.toFixed(
              6
            )}
          </div>


          {/* NDWI score (image mode only) */}
          {hoveredWaterBody.ndwiMean !== null &&
            hoveredWaterBody.ndwiMean !== undefined && (
            <div
              style={{
                fontSize: "13px",
                marginTop: "8px",
              }}
            >
              <strong>NDWI:</strong>{" "}
              {Number(hoveredWaterBody.ndwiMean).toFixed(4)}
            </div>
          )}

        </div>

      )}


      {/* =================================================
          MAP
          ================================================= */}

      <MapContainer
        center={[
          11.1271,
          78.6569,
        ]}
        zoom={7}
        style={{
          width: "100%",
          height: "100%",
        }}
      >

        <TileLayer
          attribution="© OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />


        <MapCenter
          district={
            selectedDistrict
          }
        />


        {/* NDWI fit-bounds helper */}
        <MapFitBounds geojson={ndwiGeojson} />


        {/* District water polygons */}
        {geojson && (

          <GeoJSON
            key={
              selectedDistrict?.name
            }

            data={geojson}

            style={
              waterStyle
            }

            onEachFeature={
              onEachWaterBody
            }
          />

        )}


        {/* NDWI water polygons */}
        {ndwiGeojson && ndwiGeojson.features && ndwiGeojson.features.length > 0 && (

          <GeoJSON
            key={`ndwi-${ndwiKeyRef.current}`}

            data={ndwiGeojson}

            style={waterStyle}

            onEachFeature={onEachNdwiBody}
          />

        )}

      </MapContainer>

    </div>
  );
}


export default MapView;