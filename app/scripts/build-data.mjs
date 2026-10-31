/* Snapshot the LolSuit source for the guide (port of the old tools/build_code.py, plus maps).

   Usage:  npm run data -- <path-to-main-checkout> [--ref HEAD]

   Reads committed files only (git show <ref>:<path>), so local edits and .env never leak
   into the site. Writes into public/data/:
     code-index.json  commit, repo, {path: lineCount}, symbols [name, kind, path, line]
     code.json        {path: text}, loaded lazily by the code pane
     maps.json        chains (button → api.ts → route → service → table) and the env map */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, statSync } from "node:fs";
import { dirname, join, resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(HERE, "public", "data");
const REPO_URL = "https://github.com/Avi-Lezerovich/fullstack-2026";
const SKIP_SUFFIX = [".svg", ".png", ".jpg", ".ico", "package-lock.json"];
const SKIP_NAME = new Set(["CHANGELOG.md", ".gitattributes", ".gitignore", ".dockerignore", ".coveragerc"]);

const PY_SYMBOLS = [
  [/^\s*(?:async\s+)?def\s+(\w+)/, "def"],
  [/^\s*class\s+(\w+)/, "class"],
  [/^([A-Z][A-Z0-9_]{2,})\s*(?::[^=]+)?=/, "const"],
];
const TS_SYMBOLS = [
  [/^export\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|interface|type|enum)\s+(\w+)/, "export"],
  [/^(?:const|function|let)\s+(\w+)/, "const"],
  [/^\s{2}(\w+)\s*:\s*\(.*=>/, "fn"],
];
const SQL_TABLE = /CREATE TABLE(?: IF NOT EXISTS)?\s+`?(\w+)`?/i;
const ROUTE = /@bp\.(get|post|put|patch|delete)\(\s*"([^"]+)"/;
const ENV_NAME = /"([A-Z][A-Z0-9_]{3,})"/g;
const COMPOSE_SERVICE = /^ {2}([a-z][\w-]*):\s*$/;

function git(repo, ...args) {
  return execFileSync("git", ["-C", repo, ...args], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
}

function symbolsFor(path, text) {
  const out = [];
  const lines = text.split("\n");
  if (path.endsWith(".py")) {
    lines.forEach((line, i) => {
      for (const [rx, kind] of PY_SYMBOLS) {
        const m = rx.exec(line);
        if (m) { out.push([m[1], kind, path, i + 1]); break; }
      }
      const r = ROUTE.exec(line);
      if (r) out.push([`${r[1].toUpperCase()} /api${r[2]}`, "route", path, i + 1]);
      if (path.endsWith("config.py")) for (const e of line.matchAll(ENV_NAME)) out.push([e[1], "env", path, i + 1]);
    });
  } else if ((path.endsWith(".ts") || path.endsWith(".tsx")) && !path.includes(".test.")) {
    lines.forEach((line, i) => {
      for (const [rx, kind] of TS_SYMBOLS) {
        const m = rx.exec(line);
        if (m) { out.push([m[1], kind, path, i + 1]); break; }
      }
    });
  } else if (path.endsWith(".sql")) {
    lines.forEach((line, i) => { const m = SQL_TABLE.exec(line); if (m) out.push([m[1], "table", path, i + 1]); });
  } else if (path === "docker-compose.yml") {
    let inServices = false;
    lines.forEach((line, i) => {
      if (line.startsWith("services:")) inServices = true;
      else if (line && !line.startsWith(" ") && !line.startsWith("#")) inServices = false;
      const m = COMPOSE_SERVICE.exec(line);
      if (m && inServices) out.push([m[1], "service", path, i + 1]);
    });
  }
  return out;
}

const isTest = (p) => /\/tests\/|\.test\.tsx?$|\/test\/|^server\/evals\//.test(p);
const lineOf = (text, index) => text.slice(0, index).split("\n").length;

/* A Python top-level def: its line and body, up to the next top-level statement. */
function pyBlocks(text) {
  const lines = text.split("\n"), blocks = {};
  lines.forEach((line, i) => {
    const m = /^(?:async\s+)?def\s+(\w+)/.exec(line);
    if (!m) return;
    let end = i + 1;
    while (end < lines.length && (lines[end] === "" || /^[\s)#]/.test(lines[end]))) end++;
    blocks[m[1]] = { line: i + 1, body: lines.slice(i, end).join("\n") };
  });
  return blocks;
}

/* ---------- chains: client function → route → service → tables ---------- */
function buildChains(files, tables) {
  const api = files["client/src/api.ts"] || "";
  const routes = [];
  for (const [path, text] of Object.entries(files)) {
    if (!/^server\/app\/api\/\w+\.py$/.test(path)) continue;
    const blocks = pyBlocks(text), lines = text.split("\n");
    lines.forEach((line, i) => {
      const r = ROUTE.exec(line);
      if (!r) return;
      let j = i + 1, auth = "";
      while (j < lines.length && !/^(?:async\s+)?def\s+/.test(lines[j])) {
        const a = /@security\.(\w+)/.exec(lines[j]); if (a) auth = a[1];
        j++;
      }
      const handler = (/^(?:async\s+)?def\s+(\w+)/.exec(lines[j] || "") || [])[1];
      const block = blocks[handler];
      routes.push({
        method: r[1].toUpperCase(), path: "/api" + r[2], key: r[1].toUpperCase() + " " + normRoute("/api" + r[2]),
        file: path, line: i + 1, handler, handlerLine: block ? block.line : j + 1, auth,
        body: block ? block.body : "",
      });
    });
  }

  const services = {};
  for (const [path, text] of Object.entries(files)) {
    const m = /^server\/app\/services\/(\w+_service)\.py$/.exec(path);
    if (m) services[m[1]] = { path, blocks: pyBlocks(text) };
  }
  const tableRx = /\b(?:FROM|JOIN|INTO|UPDATE)\s+`?(\w+)`?/gi;
  function tablesIn(body) {
    const found = new Set();
    for (const t of body.matchAll(tableRx)) if (tables[t[1]]) found.add(t[1]);
    return [...found];
  }
  function serviceCalls(body) {
    const out = [], seen = new Set();
    for (const c of body.matchAll(/\b(\w+_service)\.(\w+)\(/g)) {
      const key = c[1] + "." + c[2];
      if (seen.has(key)) continue;
      seen.add(key);
      const svc = services[c[1]], b = svc && svc.blocks[c[2]];
      if (!b) continue;
      // one level of same-module helpers, which is where most of the SQL lives
      let sql = b.body;
      for (const h of b.body.matchAll(/\b(_\w+)\(/g)) if (svc.blocks[h[1]]) sql += "\n" + svc.blocks[h[1]].body;
      out.push({ name: key, file: svc.path, line: b.line, tables: tablesIn(sql) });
    }
    return out;
  }

  // client callers: api.fn( or a bare fn( after a named import
  const clientFiles = Object.keys(files).filter((p) => p.startsWith("client/src/") && /\.tsx?$/.test(p) && !isTest(p) && p !== "client/src/api.ts");

  const chains = [];
  const fnRx = /^export (?:const (\w+) =|async function (\w+))/gm;
  const starts = [...api.matchAll(fnRx)];
  starts.forEach((s, k) => {
    const name = s[1] || s[2];
    const chunk = api.slice(s.index, k + 1 < starts.length ? starts[k + 1].index : api.length);
    let method, path;
    const req = /request[\s\S]*?\(\s*(?:"([^"]*)"|`([^`]*)`)/.exec(chunk);
    if (req && chunk.indexOf("request") < (chunk.indexOf("fetch(") + 1 || Infinity)) {
      path = req[1] ?? req[2];
      const mm = /json\(\s*"(\w+)"/.exec(chunk);
      method = mm ? mm[1] : "GET";
    } else {
      const f = /fetch\(\s*`\$\{BASE\}([^`]*)`/.exec(chunk);
      if (!f) return;
      path = f[1];
      const mm = /method:\s*"(\w+)"/.exec(chunk);
      method = mm ? mm[1] : "GET";
    }
    const cleanPath = "/api" + path.replace(/\$\{query[\s\S]*$/, "");
    const key = method + " " + normRoute(cleanPath);
    const route = routes.find((r) => r.key === key);
    const callers = [];
    const callRx = new RegExp("(?:\\bapi\\.|[^.\\w])" + name + "\\(");
    for (const f of clientFiles) {
      const lines = files[f].split("\n");
      for (let i = 0; i < lines.length; i++) {
        if (callRx.test(lines[i]) && !/^\s*(?:import|export)\b/.test(lines[i])) { callers.push({ file: f, line: i + 1 }); break; }
      }
    }
    chains.push({
      fn: name, method, path: cleanPath.replace(/\$\{(\w+)\}/g, ":$1"),
      client: { file: "client/src/api.ts", line: lineOf(api, s.index) },
      callers,
      route: route ? { file: route.file, line: route.line, handler: route.handler, handlerLine: route.handlerLine, auth: route.auth, path: route.path } : null,
      services: route ? serviceCalls(route.body) : [],
      tables: [],
    });
  });
  for (const c of chains) c.tables = [...new Set(c.services.flatMap((s) => s.tables))].map((t) => ({ name: t, file: "database/init.sql", line: tables[t] }));

  // routes no client function calls (admin tools, SSE streams, curl-only)
  const used = new Set(chains.filter((c) => c.route).map((c) => c.method + " " + normRoute(c.route.path)));
  const orphans = routes.filter((r) => !used.has(r.key)).map((r) => ({
    method: r.method, path: r.path, file: r.file, line: r.line, handler: r.handler, handlerLine: r.handlerLine, auth: r.auth,
    services: serviceCalls(r.body),
  }));
  return { chains, orphans };
}
function normRoute(p) {
  return p.replace(/<(?:\w+:)?\w+>/g, ":p").replace(/\$\{[^}]+\}/g, ":p").replace(/\/+$/, "");
}

/* ---------- env map ---------- */
function buildEnv(files) {
  const vars = {};
  const get = (name) => (vars[name] = vars[name] || { name, code: null, example: null, compose: null, prod: null, readers: [] });

  const config = files["server/app/config.py"] || "";
  config.split("\n").forEach((line, i) => {
    for (const m of line.matchAll(/_(int|float|str|bool|csv)\(\s*"([A-Z][A-Z0-9_]+)"(?:\s*,\s*([^)]*))?\)/g)) {
      const v = get(m[2]);
      if (!v.code) v.code = { kind: m[1], default: (m[3] || "").trim(), line: i + 1 };
    }
    for (const m of line.matchAll(/os\.environ\.get\(\s*"([A-Z][A-Z0-9_]+)"(?:\s*,\s*([^)]*))?\)/g)) {
      const v = get(m[1]);
      if (!v.code) v.code = { kind: "str", default: (m[2] || "").trim(), line: i + 1 };
    }
  });
  (files[".env.example"] || "").split("\n").forEach((line, i) => {
    const m = /^(#\s*)?([A-Z][A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (m) { const v = get(m[2]); if (!v.example) v.example = { value: m[3].trim(), commented: !!m[1], line: i + 1 }; }
  });
  for (const [file, slot] of [["docker-compose.yml", "compose"], ["prod/docker-compose.yml", "prod"]]) {
    (files[file] || "").split("\n").forEach((line, i) => {
      for (const m of line.matchAll(/\$\{([A-Z][A-Z0-9_]+)(?:(:?[-?])([^}]*))?\}/g)) {
        const v = get(m[1]);
        if (!v[slot]) v[slot] = { default: m[2] && m[2].includes("-") ? m[3] : null, required: !!(m[2] && m[2].includes("?")), line: i + 1 };
      }
    });
  }
  const codeFiles = Object.keys(files).filter((p) => /^(server|client\/src)\//.test(p) && /\.(py|tsx?)$/.test(p) && !isTest(p) && p !== "server/app/config.py");
  const readerOf = {};
  // which Settings field holds the variable: `field=_int("NAME"...` → readers use settings.field
  for (const m of config.matchAll(/(\w+)\s*=\s*_(?:int|float|str|bool|csv)\(\s*"([A-Z][A-Z0-9_]+)"/g)) readerOf[m[2]] = m[1];
  for (const v of Object.values(vars)) {
    const field = readerOf[v.name];
    v.field = field || null;
    const rx = new RegExp("\\b" + v.name + "\\b" + (field ? "|\\.(?:" + field + ")\\b" : ""));
    for (const f of codeFiles) {
      const lines = files[f].split("\n");
      for (let i = 0; i < lines.length && v.readers.length < 8; i++) if (rx.test(lines[i])) { v.readers.push({ file: f, line: i + 1 }); break; }
      if (v.readers.length >= 8) break;
    }
  }
  return Object.values(vars).sort((a, b) => a.name.localeCompare(b.name));
}

function main() {
  const args = process.argv.slice(2);
  if (!args[0]) { console.log("usage: npm run data -- <path-to-main-checkout> [--ref HEAD]"); process.exit(2); }
  const repo = resolve(args[0]);
  const ref = args[1] === "--ref" && args[2] ? args[2] : "HEAD";
  const commit = git(repo, "rev-parse", "--short", ref).trim();
  const paths = git(repo, "ls-tree", "-r", "--name-only", ref).split("\n").filter(Boolean)
    .filter((p) => !SKIP_SUFFIX.some((s) => p.endsWith(s)) && !SKIP_NAME.has(basename(p))).sort();
  const files = {}, symbols = [];
  for (const p of paths) {
    const text = git(repo, "show", `${ref}:${p}`).replace(/\r\n/g, "\n");
    files[p] = text;
    symbols.push(...symbolsFor(p, text));
  }
  const tables = Object.fromEntries(symbols.filter((s) => s[1] === "table").map((s) => [s[0], s[3]]));
  const meta = { commit, repo: REPO_URL, files: Object.fromEntries(Object.entries(files).map(([p, t]) => [p, t.split("\n").length])), symbols };
  const { chains, orphans } = buildChains(files, tables);
  const env = buildEnv(files);

  mkdirSync(OUT, { recursive: true });
  const write = (name, data) => {
    writeFileSync(join(OUT, name), JSON.stringify(data));
    console.log(`${name}: ${Math.round(statSync(join(OUT, name)).size / 1024)} KB`);
  };
  write("code-index.json", meta);
  write("code.json", files);
  write("maps.json", { commit, chains, orphans, env });
  const linked = chains.filter((c) => c.route).length;
  console.log(`${paths.length} files, ${symbols.length} symbols, commit ${commit}`);
  console.log(`${chains.length} client API functions (${linked} matched to a route), ${orphans.length} routes with no client caller, ${env.length} env vars`);
}

main();
