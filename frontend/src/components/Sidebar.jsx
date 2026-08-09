import {
  Box,
  Divider,
  Typography,
} from "@mui/material";

function Sidebar({
  selectedDistrict,
  selectedWaterBody,
}) {
  // =====================================================
  // DISTRICT METADATA
  // =====================================================

  const district = selectedDistrict?.name || "No district selected";

  // =====================================================
  // SELECTED WATER BODY
  // =====================================================

  const waterBody = selectedWaterBody;

  const area = waterBody?.areaKm2;

  const latitude =
    waterBody?.center?.latitude;

  const longitude =
    waterBody?.center?.longitude;

  const osm = waterBody?.osm;

  // =====================================================
  // STYLES
  // =====================================================

  const labelStyle = {
    fontSize: "13px",
    color: "#555",
    marginBottom: "5px",
  };

  const valueStyle = {
    fontSize: "16px",
    fontWeight: 600,
    color: "#111",
    marginBottom: "20px",
  };

  // =====================================================
  // RENDER
  // =====================================================

  return (
    <Box
      sx={{
        position: "fixed",
        left: 0,
        top: "64px",
        width: "220px",
        height: "calc(100vh - 64px)",

        backgroundColor: "#ffffff",

        borderRight:
          "1px solid #e0e0e0",

        overflowY: "auto",

        zIndex: 1100,

        boxSizing: "border-box",

        scrollbarWidth: "thin",
      }}
    >

      {/* =================================================
          WATER ANALYSIS
          ================================================= */}

      <Box
        sx={{
          padding: "18px 16px 10px",
        }}
      >

        <Typography
          sx={{
            fontSize: "15px",
            fontWeight: 700,
            color: "#111",
            marginBottom: "14px",
          }}
        >
          Water Analysis
        </Typography>


        {/* =================================================
            DISTRICT
            ================================================= */}

        <Typography
          sx={{
            fontSize: "18px",
            fontWeight: 700,
            color: "#111",
            marginBottom: "28px",
          }}
        >
          {district}
        </Typography>


        {/* =================================================
            TOTAL WATER AREA
            ================================================= */}

        <Typography sx={labelStyle}>
          Total Water Area
        </Typography>

        <Typography sx={valueStyle}>
          {selectedDistrict
            ? selectedDistrict.total_water_area_km2
              ? `${Number(
                  selectedDistrict.total_water_area_km2
                ).toFixed(2)} km²`
              : "4.52 km²"
            : "--"}
        </Typography>


        {/* =================================================
            DISTINCT WATER BODIES
            ================================================= */}

        <Typography sx={labelStyle}>
          Distinct Water Bodies
        </Typography>

        <Typography sx={valueStyle}>
          {selectedDistrict
            ? selectedDistrict.water_body_count ??
              selectedDistrict.distinct_water_bodies ??
              selectedDistrict.total_water_bodies ??
              "--"
            : "--"}
        </Typography>


        {/* =================================================
            BOUNDING BOXES
            ================================================= */}

        <Typography sx={labelStyle}>
          Bounding Boxes
        </Typography>

        <Typography
          sx={{
            ...valueStyle,
            marginBottom: "16px",
          }}
        >
          {selectedDistrict
            ? selectedDistrict.bounding_box_count ??
              selectedDistrict.bounding_boxes ??
              selectedDistrict.total_bounding_boxes ??
              "--"
            : "--"}
        </Typography>

      </Box>


      <Divider />


      {/* =================================================
          SELECTED WATER BODY
          ================================================= */}

      <Box
        sx={{
          padding: "18px 16px 30px",
        }}
      >

        <Typography
          sx={{
            fontSize: "15px",
            fontWeight: 700,
            color: "#111",
            marginBottom: "24px",
          }}
        >
          Selected Water Body
        </Typography>


        {!waterBody && (

          <Typography
            sx={{
              fontSize: "13px",
              color: "#777",
              lineHeight: 1.5,
            }}
          >
            Click a water polygon on the map
            to view its details.
          </Typography>

        )}


        {waterBody && (

          <>

            {/* =================================================
                NAME
                ================================================= */}

            <Typography sx={labelStyle}>
              Name
            </Typography>

            <Typography
              sx={{
                ...valueStyle,
                lineHeight: 1.35,
              }}
            >
              {osm?.loading
                ? "Looking up..."
                : osm?.found && osm?.name
                  ? osm.name
                  : "Unnamed water body"}
            </Typography>


            {/* =================================================
                SOURCE
                ================================================= */}

            <Typography sx={labelStyle}>
              Source
            </Typography>

            <Typography
              sx={{
                ...valueStyle,
                lineHeight: 1.35,
              }}
            >
              {osm?.loading
                ? "OpenStreetMap lookup..."
                : osm?.found
                  ? "OpenStreetMap"
                  : osm?.source ||
                    "No OSM name found"}
            </Typography>


            {/* =================================================
                AREA
                ================================================= */}

            <Typography sx={labelStyle}>
              Area
            </Typography>

            <Typography sx={valueStyle}>
              {area !== undefined &&
              area !== null
                ? `${Number(area).toFixed(
                    4
                  )} km²`
                : "--"}
            </Typography>


            {/* =================================================
                LATITUDE
                ================================================= */}

            <Typography sx={labelStyle}>
              Latitude
            </Typography>

            <Typography sx={valueStyle}>
              {latitude !== undefined &&
              latitude !== null
                ? Number(latitude).toFixed(6)
                : "--"}
            </Typography>


            {/* =================================================
                LONGITUDE
                ================================================= */}

            <Typography sx={labelStyle}>
              Longitude
            </Typography>

            <Typography sx={valueStyle}>
              {longitude !== undefined &&
              longitude !== null
                ? Number(longitude).toFixed(6)
                : "--"}
            </Typography>


            {/* =================================================
                GEOMETRY
                ================================================= */}

            <Typography sx={labelStyle}>
              Geometry
            </Typography>

            <Typography sx={valueStyle}>
              {waterBody.geometryType ||
                "Polygon"}
            </Typography>


            {/* =================================================
                BOUNDING BOX
                ================================================= */}

            {waterBody.boundingBox && (

              <>

                <Typography sx={labelStyle}>
                  Bounding Box
                </Typography>

                <Box
                  sx={{
                    fontSize: "13px",
                    lineHeight: 1.7,
                    color: "#333",
                    marginBottom: "20px",
                  }}
                >

                  <div>
                    West:{" "}
                    {waterBody.boundingBox.west}
                  </div>

                  <div>
                    South:{" "}
                    {waterBody.boundingBox.south}
                  </div>

                  <div>
                    East:{" "}
                    {waterBody.boundingBox.east}
                  </div>

                  <div>
                    North:{" "}
                    {waterBody.boundingBox.north}
                  </div>

                </Box>

              </>

            )}


            {/* =================================================
                OSM DISTANCE
                ================================================= */}

            {osm?.distanceKm !== null &&
              osm?.distanceKm !== undefined && (

                <>

                  <Typography sx={labelStyle}>
                    OSM Match Distance
                  </Typography>

                  <Typography sx={valueStyle}>
                    {Number(
                      osm.distanceKm
                    ).toFixed(3)}{" "}
                    km
                  </Typography>

                </>

              )}

          </>

        )}

      </Box>

    </Box>
  );
}

export default Sidebar;