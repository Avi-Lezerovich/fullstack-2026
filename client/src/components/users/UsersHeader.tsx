import { Box, Typography } from "@mui/material";

const UsersHeader = () => (
  <Box sx={{ mb: 3, textAlign: "center" }}>
    <Typography variant="h3" component="h1" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 900, color: "primary.dark" }}>
      לוח התובעים
    </Typography>
    <Typography sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic" }}>
      רשימת כל מי שהביא תביעה לבית המשפט. חפש שם או אימייל.
    </Typography>
  </Box>
);

export default UsersHeader;
