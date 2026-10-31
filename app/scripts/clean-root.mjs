/* Remove the previous build from the branch root before vite writes the new one.
   Only build output is touched: app/, README.md, .nojekyll and .git stay. */
import { rmSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const OUTPUT = ["index.html", "exam.html", "sw.js", "manifest.webmanifest", "assets", "data", "img"];
for (const name of OUTPUT) {
  const p = join(ROOT, name);
  if (existsSync(p)) rmSync(p, { recursive: true, force: true });
}
console.log("cleaned previous build from", ROOT);
