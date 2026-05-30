/**
 * Application entry point. Builds the provider stack and mounts <App />.
 *
 * Provider ordering:
 *   CacheProvider (RTL Emotion cache — flips MUI styles for Hebrew)
 *     └ ThemeProvider (MUI theme)
 *         └ CssBaseline (must be inside ThemeProvider to read theme tokens)
 *             └ HashRouter (client-side routing)
 *                 └ App
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { ThemeProvider, CssBaseline } from "@mui/material";
import { CacheProvider } from "@emotion/react";
import createCache from "@emotion/cache";
import { prefixer } from "stylis";
import rtlPlugin from "stylis-plugin-rtl";

import App from "./App";
import { theme } from "./theme";

// Emotion cache configured for RTL — required by MUI to flip styles (margins,
// borders, etc.) correctly for Hebrew.
const cacheRtl = createCache({
  key: "muirtl",
  stylisPlugins: [prefixer, rtlPlugin],
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CacheProvider value={cacheRtl}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <HashRouter>
          <App />
        </HashRouter>
      </ThemeProvider>
    </CacheProvider>
  </React.StrictMode>,
);
