import { useState } from "react";
import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import GavelIcon from "@mui/icons-material/Gavel";
import MenuIcon from "@mui/icons-material/Menu";
import { Link as RouterLink, useLocation, useNavigate } from "react-router-dom";

import MessagesLink from "./MessagesLink";
import NotificationBell from "./NotificationBell";
import { useAuth } from "../../context/AuthContext";
import { useNotifications } from "../../context/NotificationContext";
import { initials } from "../../utils/format";

const BASE = import.meta.env.BASE_URL;

const NAV_LINKS = [
  { to: "/", label: "בית" },
  { to: "/users", label: "תובעים" },
  { to: "/about", label: "אודות" },
];

const isActive = (pathname: string, to: string): boolean =>
  to === "/" ? pathname === "/" : pathname.startsWith(to);

/** Parchment-on-purple, so the AppBar's own text reads against the purple. */
const INK = "primary.contrastText";
const HOVER = { backgroundColor: "rgba(250, 246, 233, 0.08)" };

/**
 * TopBar — appears on every page.
 *
 * The logo links home. From sm upwards the nav links sit inline; below that
 * they collapse into a right-anchored drawer behind the hamburger, which also
 * absorbs the actions that are too wide for a phone toolbar (file a lawsuit,
 * profile, logout).
 *
 * Identity comes from `useAuth`, and notifications from `useNotifications` —
 * the same two providers every page reads. This used to keep its own copies of
 * both (a module-level `useCurrentUser` cache and a second `useNotifications`
 * hook), which meant signing in updated the pages but not the app bar, signing
 * out updated the app bar but not the pages, and every tab held two SSE
 * connections. There is one source for each now, so they cannot disagree.
 */
const TopBar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { notifications, unreadCount, markRead, latestMessageId } = useNotifications();

  const handleLogout = async () => {
    setDrawerOpen(false);
    // signOut clears the context even if the request failed — the user asked
    // to be signed out, so the UI must not keep showing them as signed in.
    await signOut();
    navigate("/");
  };

  return (
    <>
      <AppBar position="sticky">
        <Toolbar sx={{ gap: 1 }}>
          {/* The hamburger replaces the inline links below the sm breakpoint. */}
          <IconButton
            edge="start"
            onClick={() => setDrawerOpen(true)}
            aria-label="תפריט"
            sx={{ color: INK, display: { xs: "inline-flex", sm: "none" } }}
          >
            <MenuIcon />
          </IconButton>

          <Box
            component={RouterLink}
            to="/"
            sx={{ display: "flex", alignItems: "center", flexShrink: 0 }}
            aria-label="LolSuit — לעמוד הבית"
          >
            <Box
              component="img"
              src={`${BASE}lolsuit-lockup-horizontal-light.svg`}
              alt="LolSuit"
              sx={{ height: { xs: 32, sm: 42 }, display: "block" }}
            />
          </Box>

          <Box sx={{ flex: 1 }} />

          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{ display: { xs: "none", sm: "flex" } }}
          >
            {NAV_LINKS.map((link) => (
              <Button
                key={link.to}
                component={RouterLink}
                to={link.to}
                sx={{
                  color: INK,
                  fontWeight: isActive(location.pathname, link.to) ? 700 : 400,
                  "&:hover": HOVER,
                }}
              >
                {link.label}
              </Button>
            ))}
            {user?.is_admin && (
              <Button
                component={RouterLink}
                to="/admin"
                sx={{
                  color: INK,
                  fontWeight: isActive(location.pathname, "/admin") ? 700 : 400,
                  "&:hover": HOVER,
                }}
              >
                לשכת הפיקוח
              </Button>
            )}
          </Stack>

          {user ? (
            <Stack direction="row" spacing={0.5} alignItems="center">
              <MessagesLink messageSignal={latestMessageId} />
              <NotificationBell
                notifications={notifications}
                unreadCount={unreadCount}
                markRead={markRead}
              />
              <Button
                component={RouterLink}
                to="/cases/new"
                variant="contained"
                color="secondary"
                startIcon={<GavelIcon />}
                data-testid="file-case-button"
                sx={{ display: { xs: "none", sm: "inline-flex" } }}
              >
                הגשת תביעה
              </Button>
              <Tooltip title={user.name}>
                <IconButton
                  component={RouterLink}
                  to={`/users/${user.id}`}
                  sx={{ p: 0.5 }}
                  aria-label="הפרופיל שלי"
                  data-testid="profile-link"
                >
                  <Avatar
                    src={user.avatar_url ?? undefined}
                    sx={{ width: 32, height: 32, bgcolor: "secondary.main", color: "#1A2E4F" }}
                  >
                    {initials(user.name)}
                  </Avatar>
                </IconButton>
              </Tooltip>
              <Button
                onClick={handleLogout}
                data-testid="logout-button"
                sx={{
                  color: INK,
                  border: "1px solid rgba(250, 246, 233, 0.3)",
                  display: { xs: "none", sm: "inline-flex" },
                  "&:hover": HOVER,
                }}
              >
                התנתקות
              </Button>
            </Stack>
          ) : (
            <Button
              component={RouterLink}
              to="/login"
              variant="contained"
              color="secondary"
              data-testid="login-cta"
            >
              התחברות
            </Button>
          )}
        </Toolbar>
      </AppBar>

      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        {/* Clicking anywhere inside closes the drawer, so every row gets the
            behaviour without wiring onClick onto each one. */}
        <Box sx={{ width: 260 }} role="presentation" onClick={() => setDrawerOpen(false)}>
          <Box sx={{ px: 2, py: 2 }}>
            <Box
              component="img"
              src={`${BASE}lolsuit-lockup-horizontal.svg`}
              alt="LolSuit"
              sx={{ height: 34, display: "block" }}
            />
          </Box>
          <Divider />

          <List>
            {NAV_LINKS.map((link) => (
              <ListItemButton
                key={link.to}
                component={RouterLink}
                to={link.to}
                selected={isActive(location.pathname, link.to)}
              >
                <ListItemText primary={link.label} />
              </ListItemButton>
            ))}
          </List>
          <Divider />

          <List>
            {user ? (
              <>
                <ListItemButton component={RouterLink} to="/cases/new">
                  <ListItemText primary="הגשת תביעה" />
                </ListItemButton>
                <ListItemButton component={RouterLink} to="/messages">
                  <ListItemText primary="הודעות" />
                </ListItemButton>
                <ListItemButton component={RouterLink} to={`/users/${user.id}`}>
                  <ListItemText primary="הפרופיל שלי" />
                </ListItemButton>
                {user.is_admin && (
                  <ListItemButton component={RouterLink} to="/admin">
                    <ListItemText primary="לשכת הפיקוח" />
                  </ListItemButton>
                )}
                <ListItemButton onClick={handleLogout}>
                  <ListItemText primary="התנתקות" />
                </ListItemButton>
              </>
            ) : (
              <>
                <ListItemButton component={RouterLink} to="/login">
                  <ListItemText primary="התחברות" />
                </ListItemButton>
                <ListItemButton component={RouterLink} to="/signup">
                  <ListItemText primary="הרשמה" />
                </ListItemButton>
              </>
            )}
          </List>
        </Box>
      </Drawer>
    </>
  );
};

export default TopBar;
