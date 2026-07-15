import { defineConfig } from "cypress";

/**
 * Cypress E2E configuration.
 *
 * The app runs as two dev servers during E2E:
 *   - Vite client on http://localhost:8080  (proxies /api -> Flask)
 *   - Flask API  on http://localhost:5001   (talks to MySQL)
 * Cypress drives a real browser against the client origin; nothing is mocked.
 */
export default defineConfig({
  // The spec never reads Cypress.env(), so opt out of exposing it to browser code
  // (insecure default; Cypress warns until this is disabled).
  allowCypressEnv: false,
  e2e: {
    baseUrl: "http://localhost:8080",
    specPattern: "cypress/e2e/**/*.cy.{js,ts}",
    supportFile: false,
    video: false,
    screenshotOnRunFailure: true,
  },
});
