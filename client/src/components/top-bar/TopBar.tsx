import { AppBar, Box, Toolbar } from "@mui/material";
import { TopBarLogo } from "./TopBarLogo";
import { TopBarDesktopNav } from "./TopBarDesktopNav";
const TopBar = () => (
  <AppBar
    position="sticky"
    elevation={0}
    sx={{
      bgcolor: "#132238",
      backgroundImage: "linear-gradient(135deg, #132238 0%, #1f3657 100%)",
      borderBottom: "1px solid rgba(250, 246, 233, 0.12)",
    }}
  >
    <Toolbar sx={{ gap: 2, minHeight: 72 }}>
      <TopBarLogo />
      <Box sx={{ flex: 1 }} />
      <TopBarDesktopNav />
    </Toolbar>
  </AppBar>
);

export default TopBar;
