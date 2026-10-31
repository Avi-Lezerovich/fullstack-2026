import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import contentPlugin from "./plugins/content";

const root = __dirname;

// Two pages = two windows. The build lands in the branch root (..), which GitHub Pages
// serves as-is; scripts/clean-root.mjs removes the previous build first, since
// emptyOutDir would also wipe app/ and README.md.
export default defineConfig({
  base: "./",
  plugins: [react(), contentPlugin(root)],
  build: {
    outDir: resolve(root, ".."),
    emptyOutDir: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      input: { index: resolve(root, "index.html"), exam: resolve(root, "exam.html") },
    },
  },
  server: { port: 5180 },
});
