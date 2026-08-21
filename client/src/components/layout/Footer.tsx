import { Box, Container, Stack, Typography } from "@mui/material";

const PARCHMENT_DIM = "rgba(250, 246, 233, 0.7)";

/**
 * Credit strip rendered at the bottom of every page.
 * Mirrors the purple + brass-gold styling of the AppBar (gold top-border ↔ AppBar's
 * gold bottom-border) so the page feels bookended.
 */
const Footer = () => {
  return (
    <Box
      component="footer"
      sx={{
        mt: "auto",
        backgroundColor: "primary.main",
        borderTop: "3px solid",
        borderTopColor: "secondary.main",
        color: "background.default",
        py: 2.5,
      }}
    >
      <Container maxWidth="lg">
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1.5}
          alignItems="center"
          justifyContent="space-between"
        >
          <Stack direction="row" spacing={1} alignItems="center">
            <Box
              component="img"
              src={`${import.meta.env.BASE_URL}lolsuit-seal.svg`}
              alt=""
              sx={{ height: 32, width: 32, filter: "brightness(0) invert(1)" }}
            />
            <Typography
              sx={{
                fontFamily: '"Frank Ruhl Libre", serif',
                fontWeight: 700,
                color: "background.default",
              }}
            >
              LolSuit
            </Typography>
          </Stack>

          <Typography
            variant="body2"
            align="center"
            sx={{ color: PARCHMENT_DIM, maxWidth: 460 }}
          >
            בית המשפט לתביעות מצחיקות. כל התיקים בדיוניים, כל פסקי הדין סופיים.
          </Typography>

          <Typography variant="caption" sx={{ color: PARCHMENT_DIM }}>
            Mid term project · Full-Stack @ RUNI · 2026
          </Typography>
        </Stack>
      </Container>
    </Box>
  );
};

export default Footer;
