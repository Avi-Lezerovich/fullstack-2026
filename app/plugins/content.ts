/* The guide's text lives in content/*.html (one file per topic, with
   `<!-- @include path -->` for the finder groups and the recipes). This plugin turns them
   into `virtual:topics` and, on every build, checks each `<code>path:line</code>` reference
   against public/data/code-index.json (port of the old tools/build.py check_refs). */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import type { Plugin } from "vite";

const VIRTUAL = "virtual:topics";
const RESOLVED = "\0" + VIRTUAL;
const INCLUDE = /^[ \t]*<!-- @include (\S+) -->[ \t]*$/gm;
const CODE_REF = /<code>([\w./-]+\.(?:py|tsx?|sql|ya?ml|template|sh|json|txt|ini))(?::(\d+)(?:[–-](\d+))?)?<\/code>/g;
// Mentioned on purpose although they are not in the code snapshot.
const NOT_IN_SNAPSHOT = new Set(["client/src/pages/Rules.tsx", "worker.py", "CHANGELOG.md"]);

export interface Topic { id: string; num: number; title: string; heading: string; html: string; studied: boolean }

function expand(path: string, seen: string[] = []): string {
  if (seen.includes(path)) throw new Error("include cycle: " + [...seen, path].join(" -> "));
  const text = readFileSync(path, "utf8").replace(/\r\n/g, "\n");
  return text.replace(INCLUDE, (_m, rel: string) => {
    const target = resolve(dirname(path), rel);
    if (!existsSync(target)) throw new Error(`${path}: @include ${rel} not found`);
    return expand(target, [...seen, path]).replace(/\n+$/, "");
  });
}

function parseTopic(html: string, file: string): Topic {
  const head = /<section class="topic" id="(t\d+)" data-title="([^"]+)">/.exec(html);
  const num = /<div class="n">(\d+)<\/div><h2>([\s\S]*?)<\/h2>/.exec(html);
  const start = html.indexOf('<div class="topic-body">');
  const end = html.lastIndexOf("</div></section>");
  if (!head || !num || start < 0 || end < 0) throw new Error(`${file}: not a topic section`);
  return {
    id: head[1], title: head[2], num: Number(num[1]), heading: num[2],
    html: html.slice(start + '<div class="topic-body">'.length, end).trim(),
    studied: html.includes("data-done="),
  };
}

export function loadTopics(root: string): Topic[] {
  const dir = join(root, "content");
  return readdirSync(dir).filter((f) => f.endsWith(".html")).sort()
    .map((f) => parseTopic(expand(join(dir, f)), f));
}

export function checkRefs(root: string, topics: Topic[]): string[] {
  const indexPath = join(root, "public", "data", "code-index.json");
  if (!existsSync(indexPath)) return ["public/data/code-index.json is missing: run npm run data -- ../../fullstack-2026"];
  const files: Record<string, number> = JSON.parse(readFileSync(indexPath, "utf8")).files;
  const names = Object.keys(files);
  const problems: string[] = [];
  for (const t of topics) {
    for (const m of t.html.matchAll(CODE_REF)) {
      const [, p, a, b] = m;
      if (NOT_IN_SNAPSHOT.has(p)) continue;
      let hits = files[p] ? [p] : names.filter((f) => f.endsWith("/" + p));
      if (hits.length > 1) hits = hits.filter((f) => !f.includes("/tests/"));
      if (hits.length !== 1) problems.push(`${t.id} ${p}: ${hits.length} files match`);
      else if (a && Number(b || a) > files[hits[0]]) problems.push(`${t.id} ${p}:${a}: past the end (${files[hits[0]]} lines)`);
    }
  }
  return problems;
}

export default function contentPlugin(root: string): Plugin {
  return {
    name: "lolsuit-content",
    resolveId(id) { return id === VIRTUAL ? RESOLVED : null; },
    load(id) {
      if (id !== RESOLVED) return null;
      const dir = join(root, "content");
      // rebuild when any content file changes in dev
      const walk = (d: string): string[] => readdirSync(d, { withFileTypes: true })
        .flatMap((e) => e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]);
      walk(dir).forEach((f) => this.addWatchFile(f));
      return "export default " + JSON.stringify(loadTopics(root)) + ";";
    },
    buildStart() {
      if (process.env.NODE_ENV === "development") return;
      const problems = checkRefs(root, loadTopics(root));
      if (problems.length) this.error("broken code references:\n  " + problems.join("\n  "));
    },
  };
}
