import { AppBar, Toolbar, Typography, Box } from "@mui/material";

function Navbar() {
  return (
    <AppBar
      position="fixed"
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
      }}
    >
      <Toolbar>
        <Typography
          variant="h6"
          sx={{
            fontWeight: "bold",
            flexGrow: 1,
          }}
        >
          🌊 AquaDetect
        </Typography>

        <Box>
          <Typography variant="body1">
            Analytics
          </Typography>
        </Box>
      </Toolbar>
    </AppBar>
  );
}

export default Navbar;