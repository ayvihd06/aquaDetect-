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
import WaterChangePanel from "./WaterChangePanel";
import HydrologyPanel from "./HydrologyPanel";
import GISExportPanel from "./GISExportPanel";




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
  analysisMode,        // controlled from Home via Navbar
  onModeChange,        // callback to update Home state
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

  // Stores latest result output for each analysis mode for GIS export
  const [lastResults, setLastResults] = useState({});


  // =======================================================
  // NDWI STATE
  // =======================================================

  const [ndwiGeojson, setNdwiGeojson] =
    useState(null);

  const [ndwiStats, setNdwiStats] =
    useState(null);

  // Key to force GeoJSON layer remount when ndwiGeojson changes
  const ndwiKeyRef = useRef(0);

  // Water Change Analysis state
  const [changeResult, setChangeResult] = useState(null);
  const [activeLayer, setActiveLayer] = useState("change"); // "change" | "before_rgb" | "after_rgb" | "before_ndwi" | "after_ndwi" | "before_mask" | "after_mask" | flood / drought layers
  const changeKeyRef = useRef(0);

  // Hydrology (Flood & Drought Monitoring) state
  const [floodResult, setFloodResult] = useState(null);
  const [droughtResult, setDroughtResult] = useState(null);
  const floodKeyRef = useRef(0);




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
        setLastResults((prev) => ({
          ...prev,
          district: {
            district: selectedDistrict?.name || "Madurai",
            source: "AquaDetect Static Water Database",
            geojson: data,
          },
        }));


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
    setLastResults((prev) => ({
      ...prev,
      ndwi: { geojson, statistics: stats, satellite_source: "Sentinel-2 Surface Reflectance", spatial_resolution_m: 10, detection_method: "NDWI (B3, B8)" },
      image: { geojson, statistics: stats, satellite_source: "Sentinel-2 Surface Reflectance", spatial_resolution_m: 10, detection_method: "NDWI (B3, B8)" },
    }));
  };


  // =======================================================
  // MODE SWITCH HANDLER
  // =======================================================

  // =======================================================
  // STATE CLEANUP HELPER
  // =======================================================

  // Called when the mode changes (either from navbar prop or from a child component).
  // Clears result/layer state that belongs to the previous mode.
  const cleanupForMode = (mode) => {
    setLocalSelectedWaterBody(null);
    setHoveredWaterBody(null);
    if (onWaterBodySelect) onWaterBodySelect(null);

    if (mode === "district") {
      setNdwiGeojson(null);
      setNdwiStats(null);
      setChangeResult(null);
      setFloodResult(null);
      setDroughtResult(null);
    } else if (mode === "ndwi") {
      setGeojson(null);
      setChangeResult(null);
      setFloodResult(null);
      setDroughtResult(null);
    } else if (mode === "water-change") {
      setNdwiGeojson(null);
      setNdwiStats(null);
      setFloodResult(null);
      setDroughtResult(null);
    } else if (mode === "flood") {
      setGeojson(null);
      setNdwiGeojson(null);
      setNdwiStats(null);
      setChangeResult(null);
      setDroughtResult(null);
    } else if (mode === "drought") {
      setGeojson(null);
      setNdwiGeojson(null);
      setNdwiStats(null);
      setChangeResult(null);
      setFloodResult(null);
    }
  };

  // handleModeSwitch — used by any child component that needs to request a mode change.
  // It notifies Home (via onModeChange) which updates the navbar and re-renders MapView
  // with the new analysisMode prop, which then triggers the effect below.
  const handleModeSwitch = (mode) => {
    if (onModeChange) onModeChange(mode);
  };

  // When analysisMode prop changes (navbar click), clean up stale state for the previous mode.
  const prevModeRef = useRef(null);
  useEffect(() => {
    if (prevModeRef.current !== analysisMode) {
      prevModeRef.current = analysisMode;
      cleanupForMode(analysisMode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisMode]);



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
            NDWI IMAGE ANALYSIS PANEL
            =============================================== */}

        {analysisMode === "ndwi" && (

          <ImageAnalysisPanel
            onNdwiResult={handleNdwiResult}
          />

        )}


        {/* ===============================================
            WATER CHANGE ANALYSIS PANEL
            =============================================== */}

        {analysisMode === "water-change" && (

          <WaterChangePanel
            selectedDistrictName={selectedDistrict?.name || "Madurai"}
            onDistrictSelect={(dName) => {
              const found = DISTRICTS.find((d) => d.name.toLowerCase() === dName.toLowerCase());
              if (found) setSelectedDistrict(found);
            }}
            onChangeResult={(data) => {
              changeKeyRef.current += 1;
              setChangeResult(data);
              setActiveLayer("change");
              setLastResults((prev) => ({ ...prev, change: data, "water-change": data }));
            }}
            activeLayer={activeLayer}
            onLayerSelect={(layerId) => setActiveLayer(layerId)}
          />

        )}


        {/* ===============================================
            FLOOD MONITORING PANEL
            =============================================== */}

        {analysisMode === "flood" && (

          <HydrologyPanel
            activeTab="flood"
            selectedDistrictName={selectedDistrict?.name || "Madurai"}
            onFloodResult={(data) => {
              floodKeyRef.current += 1;
              setFloodResult(data);
              if (data && data.tiles) {
                setActiveLayer("flood_extent");
              }
              setLastResults((prev) => ({ ...prev, flood: data }));
            }}
            onDroughtResult={() => {}}
            activeLayer={activeLayer}
            onLayerSelect={(layerId) => setActiveLayer(layerId)}
          />

        )}


        {/* ===============================================
            DROUGHT MONITORING PANEL
            =============================================== */}

        {analysisMode === "drought" && (

          <HydrologyPanel
            activeTab="drought"
            selectedDistrictName={selectedDistrict?.name || "Madurai"}
            onFloodResult={() => {}}
            onDroughtResult={(data) => {
              setDroughtResult(data);
              if (data && data.tiles && data.tiles.current_rgb) {
                setActiveLayer("drought_current_rgb");
              }
              setLastResults((prev) => ({ ...prev, drought: data }));
            }}
            activeLayer={activeLayer}
            onLayerSelect={(layerId) => setActiveLayer(layerId)}
          />

        )}


        {/* ===============================================
            GIS EXPORT PANEL
            =============================================== */}

        {analysisMode === "gis-export" && (

          <GISExportPanel
            lastResults={lastResults}
            selectedDistrictName={selectedDistrict?.name || "Madurai"}
          />

        )}




        {/* ===============================================
            NDWI SELECTED WATER BODY (ndwi mode)
            =============================================== */}

        {analysisMode === "ndwi" &&
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


        {/* GEE SATELLITE VALIDATION TILE LAYERS */}
        {analysisMode === "water-change" && changeResult && changeResult.tiles && (
          <>
            {activeLayer === "before_rgb" && changeResult.tiles.before_rgb && (
              <TileLayer key="b_rgb" url={changeResult.tiles.before_rgb} opacity={1.0} zIndex={500} />
            )}
            {activeLayer === "after_rgb" && changeResult.tiles.after_rgb && (
              <TileLayer key="a_rgb" url={changeResult.tiles.after_rgb} opacity={1.0} zIndex={500} />
            )}
            {activeLayer === "before_ndwi" && changeResult.tiles.before_ndwi && (
              <TileLayer key="b_ndwi" url={changeResult.tiles.before_ndwi} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "after_ndwi" && changeResult.tiles.after_ndwi && (
              <TileLayer key="a_ndwi" url={changeResult.tiles.after_ndwi} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "before_mask" && changeResult.tiles.before_mask && (
              <TileLayer key="b_mask" url={changeResult.tiles.before_mask} opacity={0.8} zIndex={500} />
            )}
            {activeLayer === "after_mask" && changeResult.tiles.after_mask && (
              <TileLayer key="a_mask" url={changeResult.tiles.after_mask} opacity={0.8} zIndex={500} />
            )}
          </>
        )}

        {/* WATER CHANGE POLYGONS */}
        {analysisMode === "water-change" && activeLayer === "change" && changeResult && changeResult.geojson && (
          <>
            <MapFitBounds geojson={changeResult.geojson.loss} />

            {/* Stable Water Polygons (Blue) */}
            {changeResult.geojson.stable && changeResult.geojson.stable.features?.length > 0 && (
              <GeoJSON
                key={`stable-${changeKeyRef.current}`}
                data={changeResult.geojson.stable}
                style={{ color: "#1D4ED8", fillColor: "#2563EB", fillOpacity: 0.55, weight: 1.5 }}
                onEachFeature={(feat, layer) => {
                  layer.bindPopup(`
                    <div style="font-family: sans-serif; font-size: 12px;">
                      <strong style="color: #1E40AF;">🔵 Stable Water Region</strong><br/>
                      <strong>Area:</strong> ${feat.properties?.area_km2 || 0} km²<br/>
                      <strong>Detected Before:</strong> Yes<br/>
                      <strong>Detected After:</strong> Yes
                    </div>
                  `);
                }}
              />
            )}

            {/* Water Loss Polygons (Red) */}
            {changeResult.geojson.loss && changeResult.geojson.loss.features?.length > 0 && (
              <GeoJSON
                key={`loss-${changeKeyRef.current}`}
                data={changeResult.geojson.loss}
                style={{ color: "#991B1B", fillColor: "#DC2626", fillOpacity: 0.7, weight: 2 }}
                onEachFeature={(feat, layer) => {
                  layer.bindPopup(`
                    <div style="font-family: sans-serif; font-size: 12px;">
                      <strong style="color: #991B1B;">🔴 Water Loss Region</strong><br/>
                      <strong>Area:</strong> ${feat.properties?.area_km2 || 0} km²<br/>
                      <strong>Detected Before:</strong> Yes<br/>
                      <strong>Detected After:</strong> No
                    </div>
                  `);
                }}
              />
            )}

            {/* Water Gain Polygons (Green) */}
            {changeResult.geojson.gain && changeResult.geojson.gain.features?.length > 0 && (
              <GeoJSON
                key={`gain-${changeKeyRef.current}`}
                data={changeResult.geojson.gain}
                style={{ color: "#15803D", fillColor: "#16A34A", fillOpacity: 0.7, weight: 2 }}
                onEachFeature={(feat, layer) => {
                  layer.bindPopup(`
                    <div style="font-family: sans-serif; font-size: 12px;">
                      <strong style="color: #166534;">🟢 Water Gain Region</strong><br/>
                      <strong>Area:</strong> ${feat.properties?.area_km2 || 0} km²<br/>
                      <strong>Detected Before:</strong> No<br/>
                      <strong>Detected After:</strong> Yes
                    </div>
                  `);
                }}
              />
            )}
          </>
        )}

        {/* FLOOD MONITORING TILE LAYERS */}
        {analysisMode === "flood" && floodResult && floodResult.tiles && (
          <>
            {activeLayer === "flood_before_sar" && floodResult.tiles.before_sar && (
              <TileLayer key="f_b_sar" url={floodResult.tiles.before_sar} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "flood_after_sar" && floodResult.tiles.after_sar && (
              <TileLayer key="f_a_sar" url={floodResult.tiles.after_sar} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "flood_sar_change" && floodResult.tiles.sar_change && (
              <TileLayer key="f_sar_chg" url={floodResult.tiles.sar_change} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "flood_perm_water" && floodResult.tiles.permanent_water && (
              <TileLayer key="f_perm_w" url={floodResult.tiles.permanent_water} opacity={0.8} zIndex={500} />
            )}
            {activeLayer === "flood_extent" && floodResult.tiles.flood_extent && (
              <TileLayer key="f_ext_tile" url={floodResult.tiles.flood_extent} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "flood_stable_water" && floodResult.tiles.stable_water && (
              <TileLayer key="f_stable_w" url={floodResult.tiles.stable_water} opacity={0.8} zIndex={500} />
            )}
          </>
        )}

        {/* FLOOD EXTENT GEOJSON VECTOR LAYER */}
        {analysisMode === "flood" && (activeLayer === "flood_geojson" || (activeLayer === "flood_extent" && !floodResult?.tiles?.flood_extent)) && floodResult && floodResult.flood_geojson && floodResult.flood_geojson.features?.length > 0 && (
          <>
            <MapFitBounds geojson={floodResult.flood_geojson} />
            <GeoJSON
              key={`flood-geojson-${floodKeyRef.current}`}
              data={floodResult.flood_geojson}
              style={{ color: "#7B1FA2", fillColor: "#9C27B0", fillOpacity: 0.7, weight: 2 }}
              onEachFeature={(feat, layer) => {
                layer.bindPopup(`
                  <div style="font-family: sans-serif; font-size: 12px;">
                    <strong style="color: #7B1FA2;">🟣 Potential Flood Extent</strong><br/>
                    <strong>Detection:</strong> Sentinel-1 SAR VV &lt; ${floodResult.sar_threshold_db} dB<br/>
                    <strong>Permanent Water Excluded:</strong> Yes (JRC GSW)<br/>
                    <strong>Status:</strong> Unconfirmed Satellite Indicator
                  </div>
                `);
              }}
            />
          </>
        )}

        {/* DROUGHT MONITORING TILE LAYERS */}
        {analysisMode === "drought" && droughtResult && droughtResult.tiles && (
          <>
            {activeLayer === "drought_current_rgb" && droughtResult.tiles.current_rgb && (
              <TileLayer key="d_rgb" url={droughtResult.tiles.current_rgb} opacity={1.0} zIndex={500} />
            )}
            {activeLayer === "drought_current_ndwi" && droughtResult.tiles.current_ndwi && (
              <TileLayer key="d_ndwi" url={droughtResult.tiles.current_ndwi} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "drought_current_ndvi" && droughtResult.tiles.current_ndvi && (
              <TileLayer key="d_ndvi" url={droughtResult.tiles.current_ndvi} opacity={0.9} zIndex={500} />
            )}
            {activeLayer === "drought_current_water" && droughtResult.tiles.current_water && (
              <TileLayer key="d_water" url={droughtResult.tiles.current_water} opacity={0.8} zIndex={500} />
            )}
          </>
        )}


      </MapContainer>

      {/* MAP BANNER FOR SATELLITE INSPECTION LAYERS */}
      {analysisMode === "water-change" && activeLayer !== "change" && (
        <div
          style={{
            position: "absolute",
            top: "20px",
            right: "20px",
            zIndex: 1000,
            background: "rgba(15, 23, 42, 0.92)",
            color: "#FFFFFF",
            padding: "10px 16px",
            borderRadius: "8px",
            boxShadow: "0 4px 14px rgba(0,0,0,0.3)",
            fontSize: "12px",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <span>
            {activeLayer.includes("rgb")
              ? "🛰️ Sentinel-2 RGB Preview (Visual Reference — B4, B3, B2)"
              : activeLayer.includes("ndwi")
                ? "🌊 NDWI Spectral Layer (Algorithm Output — B3 & B8)"
                : "💧 Binary Water Mask (NDWI >= Threshold)"}
          </span>
          <button
            onClick={() => setActiveLayer("change")}
            style={{
              background: "#2563EB",
              color: "#FFF",
              border: "none",
              borderRadius: "4px",
              padding: "4px 10px",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            ← Return to Change Map
          </button>
        </div>
      )}

      {/* MAP LEGEND (Water Change Mode) */}
      {analysisMode === "water-change" && activeLayer === "change" && (
        <div
          style={{
            position: "absolute",
            bottom: "30px",
            right: "20px",
            zIndex: 1000,
            background: "rgba(255, 255, 255, 0.95)",
            padding: "10px 14px",
            borderRadius: "8px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
            fontSize: "12px",
            fontWeight: 600,
            display: "flex",
            flexDirection: "column",
            gap: "6px",
            color: "#1E293B",
          }}
        >
          <div style={{ fontSize: "11px", color: "#64748B", textTransform: "uppercase", letterSpacing: "0.5px" }}>Change Map Legend</div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ width: "12px", height: "12px", borderRadius: "2px", backgroundColor: "#DC2626", display: "inline-block" }}></span>
            <span>🔴 Water Loss</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ width: "12px", height: "12px", borderRadius: "2px", backgroundColor: "#16A34A", display: "inline-block" }}></span>
            <span>🟢 Water Gain</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ width: "12px", height: "12px", borderRadius: "2px", backgroundColor: "#2563EB", display: "inline-block" }}></span>
            <span>🔵 Stable Water</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ width: "12px", height: "12px", borderRadius: "2px", backgroundColor: "#9CA3AF", display: "inline-block" }}></span>
            <span>⚪ No Data / Cloud</span>
          </div>
        </div>
      )}



    </div>
  );
}


export default MapView;