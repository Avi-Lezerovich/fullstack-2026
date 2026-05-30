import { Link as RouterLink, useLocation, useNavigate } from "react-router-dom";
import { AppBar, Box, Button, Stack, Toolbar, Typography } from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";

import { logout } from "../../api";
import { useCurrentUser } from "../../hooks/useCurrentUser";

const BASE = import.meta.env.BASE_URL;

const NAV_LINKS = [
  { to: "/", label: "בית" },
  { to: "/users", label: "תובעים" },
  { to: "/about", label: "אודות" },
];

const isActive = (pathname: string, to: string): boolean =>
  to === "/" ? pathname === "/" : pathname.startsWith(to);

/**
 * TopBar — appears on every page (desktop layout).
 * Logo links home; nav buttons on the right. When logged in it also shows the
 * "submit lawsuit" button, a greeting, and logout; otherwise a login CTA.
 */
const TopBar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useCurrentUser();

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <AppBar position="sticky">
      <Toolbar sx={{ gap: 2 }}>
        <Box component={RouterLink} to="/" sx={{ display: "flex", alignItems: "center", flexShrink: 0 }} aria-label="LolSuit — לעמוד הבית">
          <Box component="img" src={`${BASE}lolsuit-lockup-horizontal-light.svg`} alt="LolSuit" sx={{ height: 42, display: "block" }} />
        </Box>

        <Box sx={{ flex: 1 }} />

        <Stack direction="row" spacing={1} alignItems="center">
          {NAV_LINKS.map((link) => (
            <Button
              key={link.to}
              component={RouterLink}
              to={link.to}
              sx={{
                color: "#FAF6E9",
                fontWeight: isActive(location.pathname, link.to) ? 700 : 400,
                "&:hover": { backgroundColor: "rgba(250, 246, 233, 0.08)" },
              }}
            >
              {link.label}
            </Button>
          ))}

          {user ? (
            <>
              <Button component={RouterLink} to="/new-post" variant="contained" color="secondary" startIcon={<GavelIcon />}>
                הגש תביעה
              </Button>
              <Typography sx={{ color: "#FAF6E9", mx: 1, fontWeight: 500 }} title={user.name}>
                שלום, {user.name}
              </Typography>
              <Button
                onClick={handleLogout}
                sx={{ color: "#FAF6E9", border: "1px solid rgba(250, 246, 233, 0.3)", "&:hover": { backgroundColor: "rgba(250, 246, 233, 0.08)" } }}
              >
                שחרור באולם
              </Button>
            </>
          ) : (
            <Button component={RouterLink} to="/login" variant="contained" color="secondary">
              התייצב
            </Button>
          )}
        </Stack>
      </Toolbar>
    </AppBar>
  );
};

export default TopBar;
