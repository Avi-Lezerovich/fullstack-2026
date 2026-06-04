import { Box, Typography } from "@mui/material";

const HomeHeader = () => (
  <Box sx={{ mb: 3, textAlign: "center" }}>
    <Typography variant="h3" component="h1" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 900, color: "primary.dark" }}>
     שערי בית המשפט פתוחים
    </Typography>
    <Typography sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic" }}>
     ריכוז התביעות האחרונות שהוגשו למערכת.
    </Typography>
  </Box>
);

export default HomeHeader;
