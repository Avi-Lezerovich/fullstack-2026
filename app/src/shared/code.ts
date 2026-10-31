/* The code snapshot: index (files, symbols) loaded at start, file contents on demand.
   Port of the path/symbol helpers and grep from the old code-viewer.js. */
import { createStore } from "./store";

export type Symbol = [name: string, kind: string, path: string, line: number];
export interface CodeIndex { commit: string; repo: string; files: Record<string, number>; symbols: Symbol[] }
export interface Ref { path: string; line: number; end?: number }

const EMPTY: CodeIndex = { commit: "", repo: "", files: {}, symbols: [] };
export const indexStore = createStore<CodeIndex>(EMPTY);
export const codeStore = createStore<Record<string, string> | null>(null);

let FILES: string[] = [];
let DEFS: Record<string, Symbol[]> = {};
export let ORDERED: string[] = [];

export const isTest = (p: string) => /\/tests\/|\.test\.tsx?$|\/test\/|^server\/evals\//.test(p);

const RANK = [/^client\/src\//, /^server\/app\//, /^server\/worker\//, /^database\//, /^(docker-compose|Makefile|\.env)/, /^server\/[^/]+$/, /^client\//, /^prod\//, /\/tests\/|\.test\./, /./];
function rank(f: string) { const i = RANK.findIndex((r) => r.test(f)); return i < 0 ? RANK.length : i; }

let indexPromise: Promise<CodeIndex> | null = null;
export function loadIndex(): Promise<CodeIndex> {
  if (!indexPromise) {
    indexPromise = fetch("data/code-index.json").then((r) => r.json() as Promise<CodeIndex>).then((idx) => {
      FILES = Object.keys(idx.files);
      DEFS = {};
      idx.symbols.forEach((s) => { (DEFS[s[0]] = DEFS[s[0]] || []).push(s); });
      ORDERED = FILES.slice().sort((a, b) => rank(a) - rank(b) || (a < b ? -1 : 1));
      indexStore.set(idx);
      return idx;
    });
  }
  return indexPromise;
}

let codePromise: Promise<Record<string, string>> | null = null;
export function loadCode(): Promise<Record<string, string>> {
  if (!codePromise) {
    codePromise = loadIndex()
      .then((idx) => fetch("data/code.json?v=" + idx.commit))
      .then((r) => r.json() as Promise<Record<string, string>>)
      .then((code) => { codeStore.set(code); return code; });
    codePromise.catch(() => { codePromise = null; });
  }
  return codePromise;
}

export function files() { return FILES; }
export function lineCount(path: string) { return indexStore.get().files[path] || 0; }

export function resolvePath(p: string): string | null {
  const idx = indexStore.get();
  if (idx.files[p]) return p;
  let hits = FILES.filter((f) => f.endsWith("/" + p));
  if (hits.length > 1) hits = hits.filter((f) => !isTest(f));
  return hits.length === 1 ? hits[0] : null;
}

/* The one non-test definition of a name, or null when it is defined in several files. */
export function defOf(name: string): Symbol | null {
  const all = (DEFS[name] || []).filter((s) => !isTest(s[2]));
  if (!all.length) return null;
  return new Set(all.map((s) => s[2])).size === 1 ? all[0] : null;
}
export function defsOf(name: string): Symbol[] { return DEFS[name] || []; }

export function langOf(p: string): string | null {
  const name = p.split("/").pop() || "";
  if (/\.py$/.test(p)) return "python";
  if (/\.tsx?$/.test(p)) return "typescript";
  if (/\.sql$/.test(p)) return "sql";
  if (/\.ya?ml$/.test(p)) return "yaml";
  if (/\.sh$/.test(p) || name === "Dockerfile") return "bash";
  if (/\.md$/.test(p)) return "markdown";
  if (/\.json$/.test(p)) return "json";
  if (/\.html$/.test(p)) return "xml";
  if (name === "Makefile") return "makefile";
  if (/\.(ini|example|template)$/.test(p) || name === ".env.example") return "ini";
  return null;
}

export interface GrepOpts { regex?: boolean; caseSensitive?: boolean; where?: string; noTests?: boolean }
export interface GrepFile { path: string; hits: { line: number; text: string; at: number; len: number }[] }

export function makeRx(q: string, opts: GrepOpts): RegExp {
  return new RegExp(opts.regex ? q : q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), opts.caseSensitive ? "" : "i");
}

/* grep across the snapshot, ranked app code first, tests last. */
export function grep(code: Record<string, string>, q: string, opts: GrepOpts, cap = 400): { files: GrepFile[]; total: number; nfiles: number } {
  const rx = makeRx(q, opts);
  const where = (opts.where || "").trim().toLowerCase();
  let total = 0, nfiles = 0, shown = 0;
  const out: GrepFile[] = [];
  for (const f of ORDERED) {
    if (opts.noTests && isTest(f)) continue;
    if (where && !f.toLowerCase().includes(where)) continue;
    const lines = (code[f] || "").split("\n");
    const hits: GrepFile["hits"] = [];
    for (let i = 0; i < lines.length; i++) {
      const m = rx.exec(lines[i]);
      if (m) hits.push({ line: i + 1, text: lines[i], at: m.index, len: m[0].length });
    }
    if (!hits.length) continue;
    nfiles++; total += hits.length;
    if (shown >= cap) continue;
    const take = hits.slice(0, cap - shown);
    shown += take.length;
    out.push({ path: f, hits: take });
  }
  return { files: out, total, nfiles };
}

export function githubUrl(path: string, line?: number, end?: number) {
  const idx = indexStore.get();
  return `${idx.repo}/blob/${idx.commit}/${path}` + (line ? `#L${line}` + (end && end > line ? `-L${end}` : "") : "");
}
