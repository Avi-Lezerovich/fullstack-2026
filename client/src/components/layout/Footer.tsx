import { Box, Container, IconButton, Stack, Typography } from "@mui/material";
import GitHubIcon from "@mui/icons-material/GitHub";
import LinkedInIcon from "@mui/icons-material/LinkedIn";

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

          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="caption" sx={{ color: PARCHMENT_DIM }}>
              Final project · Full-Stack @ RUNI · 2026
            </Typography>
            <Stack direction="row" spacing={0.5}>
              <IconButton
                component="a"
                href="https://www.linkedin.com/in/avi-lezerovich"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="LinkedIn"
                sx={{ color: "background.default" }}
              >
                <LinkedInIcon />
              </IconButton>
              <IconButton
                component="a"
                href="https://github.com/Avi-Lezerovich"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="GitHub"
                sx={{ color: "background.default" }}
              >
                <GitHubIcon />
              </IconButton>
            </Stack>
          </Stack>
        </Stack>
      </Container>
    </Box>
  );
};

export default Footer;
