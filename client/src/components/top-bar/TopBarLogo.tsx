import { Box, Typography } from "@mui/material";

export const TopBarLogo = () => (
  <Box
    sx={{
      display: "flex",
      alignItems: "center",
      gap: 1.25,
      flexShrink: 0,
      color: "#FAF6E9",
    }}
  >
    <Box
      sx={{
        width: 34,
        height: 34,
        borderRadius: "50%",
        bgcolor: "secondary.main",
        display: "grid",
        placeItems: "center",
        color: "secondary.contrastText",
        fontWeight: 800,
      }}
    >
      L
    </Box>
    <Typography variant="h6" component="span" sx={{ fontWeight: 700, letterSpacing: 0.4 }}>
      LolSuit
    </Typography>
  </Box>
);
