import { createTheme } from "@mui/material/styles";
import type { ThemeOptions } from "@mui/material/styles";

const themeOptions: ThemeOptions = {
  direction: "rtl",
  palette: {
    mode: "light",
    primary: {
      main: "#3C3489",   // Court Purple — the LolSuit brand color
      dark: "#2A2466",
      light: "#5B52A6",
      contrastText: "#FAF6E9",
    },
    secondary: {
      main: "#B8860B",   // brass gold (the gavel, AppBar underline)
      dark: "#8B6508",
      light: "#D4A82A",
      contrastText: "#1A2E4F",
    },
    error: {
      main: "#B33A3A",   // Verdict Red — for "חייב"
    },
    success: {
      main: "#4A7C59",   // Acquittal Green — for "זכאי"
    },
    warning: {
      main: "#C77700",
    },
    background: {
      default: "#FAF6E9",  // parchment
      paper: "#FFFDF5",
    },
    text: {
      primary: "#1A1530",  // Ink Black
      secondary: "#5A4F3C",
    },
    divider: "rgba(60, 52, 137, 0.15)",
  },
  typography: {
    fontFamily: '"David Libre", "Frank Ruhl Libre", "Heebo", "Times New Roman", serif',
    h1: { fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, letterSpacing: "-0.02em" },
    h2: { fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, letterSpacing: "-0.01em" },
    h3: { fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700 },
    h4: { fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700 },
    h5: { fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 500 },
    h6: { fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 500 },
    button: { fontWeight: 500, textTransform: "none" },
  },
  shape: {
    borderRadius: 6,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        // Safety net: nothing should ever cause horizontal scroll. If a child
        // overflows, we'd rather clip than break the layout.
        html: { overflowX: "hidden" },
        body: {
          overflowX: "hidden",
          backgroundColor: "#FAF6E9",
          // Subtle paper-grain background using two layered radial gradients
          backgroundImage:
            "radial-gradient(circle at 20% 30%, rgba(184, 134, 11, 0.04), transparent 50%), radial-gradient(circle at 80% 70%, rgba(60, 52, 137, 0.04), transparent 50%)",
        },
      },
    },
    MuiAppBar: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        // Court Purple to match the Footer — the page is "bookended" between
        // two identical purple bars with a gold underline / overline.
        root: {
          backgroundColor: "#3C3489",
          borderBottom: "3px solid #B8860B",
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { borderRadius: 4 },
        containedSecondary: {
          color: "#1A2E4F",
          fontWeight: 700,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: "1px solid rgba(60, 52, 137, 0.14)",
          boxShadow: "0 1px 3px rgba(26, 21, 48, 0.06), 0 4px 12px rgba(26, 21, 48, 0.04)",
          transition: "box-shadow 180ms ease, transform 180ms ease",
          "@media (hover: hover)": {
            "&:hover": {
              boxShadow:
                "0 2px 6px rgba(26, 21, 48, 0.1), 0 8px 24px rgba(26, 21, 48, 0.08)",
            },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500 },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontWeight: 500,
          fontSize: "1rem",
        },
      },
    },
  },
};

/**
 * MUI theme for the application — the visual identity of the whole app.
 * Brand palette: Court Purple (primary) + parchment background + brass-gold accent.
 * The AppBar is the one deliberate exception — it stays deep-navy.
 * UI fonts: Frank Ruhl Libre (display serif, headlines) and Heebo (sans, body & UI).
 */
export const theme = createTheme(themeOptions);

// Document-body font for legal-filing passages: post bodies, charges, glossary,
// disclaimer. David Libre is the de-facto Israeli legal-document typeface.
export const DOC_FONT = '"David Libre", "Frank Ruhl Libre", "Times New Roman", serif';
