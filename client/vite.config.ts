/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // Everything the app fetches goes through /api, so one proxy rule covers
      // it. http-proxy streams responses unbuffered by default, which is what
      // lets the SSE notification stream work in development.
      // 5002 is the server's own default (server/app/config.py: PORT), and the
      // port the container publishes to loopback. It used to say 5001, which
      // matched nothing.
      "/api": {
        target: "http://localhost:5002",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    // This file exists. The previous version pointed at a setup file that was
    // never created, so `npm test` failed before running a single test.
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/main.tsx"],
    },
  },
});
