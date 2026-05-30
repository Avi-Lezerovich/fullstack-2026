import { Box, Typography } from "@mui/material";

const HomeHeader = () => (
  <Box sx={{ mb: 3, textAlign: "center" }}>
    <Typography variant="h3" component="h1" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 900, color: "primary.dark" }}>
      בית המשפט פתוח
    </Typography>
    <Typography sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic" }}>
      כל התביעות האחרונות שהוגשו לבית המשפט.
    </Typography>
  </Box>
);

export default HomeHeader;
