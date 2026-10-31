/* The code pane: one file with line numbers, the file list, grep across the project and
   "find usages" for any name. Port of the old code-viewer.js. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { HLJSApi } from "highlight.js";
import {
  codeStore, defOf, defsOf, files, githubUrl, grep, indexStore, isTest, langOf, loadCode, ORDERED,
  type GrepOpts,
} from "./code";
import { closePane, openFile, openGrep, openUsages, paneStore, type PaneTab } from "./pane";
import { useStore } from "./store";
import { copy } from "./toast";
import { loadHighlighter } from "./highlight";
import { openInVSCode } from "./vscode";

const LH = 20, PAD = 10; // code line height and top padding, in px (kept in sync with .cp-*)
const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

const TABS: [PaneTab, string][] = [["file", "קובץ"], ["files", "כל הקבצים"], ["grep", "חיפוש בקוד"], ["usages", "שימושים"]];

export default function CodePane({ docked = true }: { docked?: boolean }) {
  const s = useStore(paneStore);
  useEffect(() => { if (s.open) loadCode(); }, [s.open]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && paneStore.get().open && docked && !document.querySelector("dialog[open]")) closePane(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [docked]);
  if (docked && !s.open) return null;
  const setTab = (tab: PaneTab) => paneStore.set((p) => ({ ...p, tab }));
  return (
    <aside className={"codepane" + (docked ? " docked" : " full") + (s.wide ? " wide" : "")} aria-label="צפייה בקוד"
      onKeyDown={(e) => { if (/^Arrow/.test(e.key)) e.stopPropagation(); }}>
      <div className="cp-head">
        <div className="seg cp-tabs" role="tablist">
          {TABS.map(([t, label]) => <button key={t} type="button" aria-pressed={s.tab === t} onClick={() => setTab(t)}>{label}</button>)}
        </div>
        <span className="grow" />
        {docked && <button className="btn cp-wide" type="button" title="הרחב/צמצם" onClick={() => paneStore.set((p) => ({ ...p, wide: !p.wide }))}>⇔</button>}
        {docked && <button className="btn" type="button" aria-label="סגור" onClick={closePane}>✕ סגור</button>}
      </div>
      {s.tab === "file" && <FileView />}
      {s.tab === "files" && <FileList />}
      {s.tab === "grep" && <GrepView />}
      {s.tab === "usages" && <UsagesView />}
    </aside>
  );
}

/* ---------- one file ---------- */
function FileView() {
  const s = useStore(paneStore);
  const code = useStore(codeStore);
  const [hl, setHl] = useState<HLJSApi | null>(null);
  const [find, setFind] = useState("");
  const [findAt, setFindAt] = useState(0);
  const [usage, setUsage] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { loadHighlighter().then(setHl); }, []);
  useEffect(() => { setFind(s.term); setUsage(""); }, [s.path, s.nonce, s.term]);

  const text = s.path && code ? code[s.path] : undefined;
  const html = useMemo(() => {
    if (text == null || !s.path) return "";
    const lang = langOf(s.path);
    if (hl && lang && text.length < 300000) {
      try { return hl.highlight(text, { language: lang, ignoreIllegals: true }).value; } catch { /* plain */ }
    }
    return esc(text);
  }, [text, hl, s.path]);
  const n = text == null ? 0 : text.split("\n").length;

  const finds = useMemo(() => {
    if (!find || text == null) return [] as number[];
    const q = find.toLowerCase(), out: number[] = [];
    text.split("\n").forEach((l, i) => { if (l.toLowerCase().includes(q)) out.push(i + 1); });
    return out;
  }, [find, text]);
  useEffect(() => {
    const i = s.line ? finds.indexOf(s.line) : -1;
    setFindAt(i >= 0 ? i : 0);
  }, [finds, s.line]);

  const scrollTo = (line: number) => { if (box.current) box.current.scrollTop = Math.max(0, PAD + (line - 1) * LH - box.current.clientHeight / 3); };
  useEffect(() => { if (html) { if (s.line) scrollTo(s.line); else if (box.current) box.current.scrollTop = 0; } }, [html, s.line, s.nonce]);
  useEffect(() => { if (finds.length && find !== s.term) scrollTo(finds[findAt]); }, [findAt, finds]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!s.path) return <div className="cp-view"><div className="cp-empty">בחרו קובץ מהרשימה, מהחיפוש או מקישור במדריך.</div></div>;
  const step = (d: number) => { if (finds.length) { const i = (findAt + d + finds.length) % finds.length; setFindAt(i); scrollTo(finds[i]); } };
  const def = usage ? defOf(usage) : null;
  const usageCount = usage && code ? countUses(code, usage) : null;

  return (
    <div className="cp-view">
      <div className="cp-bar">
        <code className="cp-path">{s.path + (s.line ? ":" + s.line : "")}</code>
        <button className="btn" type="button" title="מדביקים ב־Ctrl+P ב־VS Code" onClick={() => copy(s.path + (s.line ? ":" + s.line : ""))}>העתק נתיב:שורה</button>
        <button className="btn primary" type="button" title="פותח את הקובץ, בשורה הזו, ב־VS Code במחשב שלך" onClick={() => openInVSCode(s.path!, s.line)}>פתח ב־VS Code</button>
        <a className="btn" href={githubUrl(s.path, s.line, s.end)} target="_blank" rel="noopener">GitHub ↗</a>
        <span className="cp-find">
          <input className="search" type="search" placeholder="חיפוש בקובץ (Enter = הבא)" aria-label="חיפוש בקובץ" value={find}
            onChange={(e) => setFind(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); step(e.shiftKey ? -1 : 1); } }} />
          <span className="cp-find-info">{find ? (finds.length ? `${findAt + 1}/${finds.length}` : "0") : ""}</span>
        </span>
      </div>
      <div className={"cp-usage" + (usage ? " on" : "")} aria-live="polite">
        {!usage ? <span className="cp-usage-hint">טיפ: לחיצה על שם בקוד (פונקציה, קבוע, משתנה) מראה איפה עוד משתמשים בו</span> : <>
          <code className="cp-uword">{usage}</code>
          {usageCount && <span className="cp-ucount">{usageCount.lines} שורות ב־{usageCount.files} קבצים</span>}
          {def && <button className="btn" type="button" onClick={() => openFile(def[2], def[3], def[3], usage)}>הגדרה: {def[2].split("/").pop()}:{def[3]}</button>}
          <button className="btn primary" type="button" onClick={() => openUsages(usage)}>כל השימושים</button>
          <button className="btn" type="button" aria-label="סגור" onClick={() => setUsage("")}>✕</button>
        </>}
      </div>
      <div className="cp-code" tabIndex={0} ref={box} title="לחיצה על שם: איפה עוד משתמשים בו"
        onClick={(e) => {
          const t = e.target as HTMLElement;
          const ln = t.closest("[data-ln]") as HTMLElement | null;
          if (ln) {
            const k = Number(ln.dataset.ln);
            paneStore.set((p) => ({ ...p, line: k, end: k }));
            copy(s.path + ":" + k);
            return;
          }
          if (t.closest(".cp-src") && !String(window.getSelection() || "")) {
            const w = wordAt(e.nativeEvent);
            setUsage(w && w.length >= 3 && !/^\d/.test(w) ? w : "");
          }
        }}>
        {text == null ? <div className="cp-empty">{code ? "הקובץ לא נמצא בצילום הקוד." : "טוען קוד…"}</div> : (
          <div className="cp-inner">
            <div className="cp-gutter">{Array.from({ length: n }, (_, i) => <span key={i} data-ln={i + 1}>{i + 1}</span>)}</div>
            <pre className="cp-src"><code className="hljs" dangerouslySetInnerHTML={{ __html: html }} /></pre>
            {s.line > 0 && <div className="cp-band" style={{ top: PAD + (s.line - 1) * LH, height: (s.end - s.line + 1) * LH }} />}
            {finds.map((l, i) => <div key={l} className={"cp-hit" + (i === findAt ? " cur" : "")} style={{ top: PAD + (l - 1) * LH, height: LH }} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function wordAt(e: MouseEvent): string {
  let node: Node | null = null, off = 0;
  const d = document as Document & { caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null };
  if (document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(e.clientX, e.clientY);
    if (r) { node = r.startContainer; off = r.startOffset; }
  } else if (d.caretPositionFromPoint) {
    const p = d.caretPositionFromPoint(e.clientX, e.clientY);
    if (p) { node = p.offsetNode; off = p.offset; }
  }
  if (!node || node.nodeType !== 3) return "";
  const t = node.nodeValue || "";
  let a = off, b = off;
  while (a > 0 && /\w/.test(t[a - 1])) a--;
  while (b < t.length && /\w/.test(t[b])) b++;
  return t.slice(a, b);
}

function countUses(code: Record<string, string>, word: string) {
  const rx = new RegExp("\\b" + word.replace(/[^\w]/g, "") + "\\b");
  let lines = 0, nfiles = 0;
  for (const f of ORDERED) {
    const k = (code[f] || "").split("\n").filter((l) => rx.test(l)).length;
    if (k) { lines += k; nfiles++; }
  }
  return { lines, files: nfiles };
}

/* ---------- all files ---------- */
function FileList() {
  const idx = useStore(indexStore);
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const toks = q.toLowerCase().replace(/[־_\-./:()"'`,]/g, " ").split(/\s+/).filter(Boolean);
    const out: [string, string[]][] = [];
    const at: Record<string, number> = {};
    for (const f of files()) {
      const hay = f.toLowerCase().replace(/[_\-./]/g, " ") + " " + f.toLowerCase();
      if (!toks.every((t) => hay.includes(t))) continue;
      const dir = f.includes("/") ? f.slice(0, f.lastIndexOf("/") + 1) : "/";
      if (at[dir] == null) { at[dir] = out.length; out.push([dir, []]); }
      out[at[dir]][1].push(f);
    }
    return out;
  }, [q, idx]);
  return (
    <div className="cp-view">
      <input className="search cp-filter" type="search" autoFocus placeholder="סינון קבצים, למשל NewCase או api/cases" aria-label="סינון קבצים"
        value={q} onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && groups[0]) openFile(groups[0][1][0]); }} />
      <div className="cp-list">
        {groups.length ? groups.map(([dir, fs]) => (
          <div key={dir}>
            <div className="cp-dir">{dir}</div>
            {fs.map((f) => (
              <div key={f} className="cp-file-row">
                <button type="button" className="cp-file" onClick={() => openFile(f)}>
                  <span>{dir === "/" ? f : f.slice(dir.length)}</span><small>{idx.files[f]} שורות</small>
                </button>
                <button type="button" className="cp-vs" title="פתח ב־VS Code" onClick={() => openInVSCode(f)}>VS</button>
              </div>
            ))}
          </div>
        )) : <div className="cp-empty">אין קובץ כזה.</div>}
      </div>
    </div>
  );
}

/* ---------- grep ---------- */
function GrepView() {
  const s = useStore(paneStore);
  const code = useStore(codeStore);
  const [q, setQ] = useState(s.grep.q);
  const [opts, setOpts] = useState<GrepOpts>({ noTests: false, ...s.grep.opts });
  const [live, setLive] = useState({ q: s.grep.q, opts });
  useEffect(() => { setQ(s.grep.q); const o = { noTests: false, ...s.grep.opts }; setOpts(o); setLive({ q: s.grep.q, opts: o }); }, [s.grep.nonce]);
  useEffect(() => { const t = setTimeout(() => setLive({ q, opts }), 220); return () => clearTimeout(t); }, [q, opts]);
  const result = useMemo(() => {
    if (!live.q.trim() || !code) return null;
    try { return grep(code, live.q, live.opts); } catch (e) { return { error: (e as Error).message }; }
  }, [live, code]);
  const set = (k: keyof GrepOpts, v: boolean | string) => setOpts((o) => ({ ...o, [k]: v }));
  const term = live.opts.regex ? live.q.replace(/\\b/g, "") : live.q;
  return (
    <div className="cp-view">
      <form className="cp-grepform" onSubmit={(e) => { e.preventDefault(); setLive({ q, opts }); }}>
        <input className="search cp-q" type="search" autoFocus placeholder="טקסט לחיפוש בכל הקבצים, למשל איסוף עדויות או MIN_PASSWORD" aria-label="חיפוש בכל הקוד"
          value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="cp-opts">
          <input className="search cp-where" type="text" placeholder="רק בנתיב: client/ או .py" aria-label="סינון נתיב" value={opts.where || ""} onChange={(e) => set("where", e.target.value)} />
          <label><input type="checkbox" checked={!!opts.noTests} onChange={(e) => set("noTests", e.target.checked)} /> בלי טסטים</label>
          <label><input type="checkbox" checked={!!opts.caseSensitive} onChange={(e) => set("caseSensitive", e.target.checked)} /> רגיש לאותיות</label>
          <label><input type="checkbox" checked={!!opts.regex} onChange={(e) => set("regex", e.target.checked)} /> regex</label>
          {q && <button type="button" className="btn" title="אותו חיפוש בטרמינל" onClick={() => copy(`git grep -n${opts.caseSensitive ? "" : "i"}${opts.regex ? "E" : "F"} "${q.replace(/"/g, '\\"')}"${opts.where ? " -- " + opts.where : ""}`)}>העתק כ־git grep</button>}
        </div>
      </form>
      <div className="cp-ginfo">
        {!code && live.q ? "טוען קוד…" : result && "error" in result ? "regex לא תקין: " + result.error :
          result ? (result.total ? `${result.total} התאמות ב־${result.nfiles} קבצים` + (result.total > 400 ? " (מוצגות 400 הראשונות, צמצמו עם סינון נתיב)" : "") : "אין התאמות.") : ""}
      </div>
      <div className="cp-results">
        {result && "files" in result && result.files.map((f) => (
          <div key={f.path}>
            <div className="cp-gfile">
              <button type="button" className="cp-gpath" onClick={() => openFile(f.path)}>{f.path}</button>
              <span className="cnt">{f.hits.length}</span>{isTest(f.path) && <span className="t">טסט</span>}
              <button type="button" className="cp-vs" title="פתח ב־VS Code" onClick={() => openInVSCode(f.path, f.hits[0].line)}>VS</button>
            </div>
            {f.hits.map((h) => <GrepRow key={h.line} path={f.path} hit={h} term={/^[\w֐-׿ .-]+$/.test(term) ? term : ""} />)}
          </div>
        ))}
      </div>
    </div>
  );
}

function GrepRow({ path, hit, term }: { path: string; hit: { line: number; text: string; at: number; len: number }; term: string }) {
  const from = Math.max(0, hit.at - 70);
  const pre = (from ? "…" : "") + hit.text.slice(from, hit.at);
  const mid = hit.text.slice(hit.at, hit.at + hit.len);
  const post = hit.text.slice(hit.at + hit.len, from + 200);
  return (
    <div className="cp-gl-row">
      <button type="button" className="cp-gl" onClick={() => openFile(path, hit.line, hit.line, term)}>
        <span className="n">{hit.line}</span><code>{pre.trimStart()}<mark>{mid}</mark>{post}</code>
      </button>
      <button type="button" className="cp-vs" title="פתח ב־VS Code בשורה הזו" onClick={() => openInVSCode(path, hit.line)}>VS</button>
    </div>
  );
}

/* ---------- find usages (tool 1) ---------- */
function UsagesView() {
  const s = useStore(paneStore);
  const code = useStore(codeStore);
  const [name, setName] = useState(s.usage);
  const [noTests, setNoTests] = useState(true);
  useEffect(() => setName(s.usage), [s.usage]);
  const word = name.trim().replace(/[^\w]/g, "");
  const defs = word ? defsOf(word) : [];
  const result = useMemo(() => {
    if (!word || !code) return null;
    return grep(code, "\\b" + word + "\\b", { regex: true, caseSensitive: true, noTests }, 600);
  }, [word, code, noTests]);
  const defKeys = new Set(defs.map((d) => d[2] + ":" + d[3]));
  return (
    <div className="cp-view">
      <form className="cp-grepform" onSubmit={(e) => { e.preventDefault(); openUsages(name); }}>
        <input className="search cp-q" type="search" autoFocus placeholder="שם פונקציה, קבוע, משתנה או טבלה: MIN_PASSWORD_LENGTH, toggle_like, likes" aria-label="שם לחיפוש שימושים"
          value={name} onChange={(e) => setName(e.target.value)} />
        <div className="cp-opts">
          <label><input type="checkbox" checked={noTests} onChange={(e) => setNoTests(e.target.checked)} /> בלי טסטים</label>
          {word && <button type="button" className="btn" onClick={() => openGrep("\\b" + word + "\\b", { regex: true, caseSensitive: true })}>פתח כחיפוש</button>}
          {word && <button type="button" className="btn" onClick={() => copy(`git grep -nw "${word}"`)}>העתק כ־git grep</button>}
        </div>
      </form>
      <div className="cp-results">
        {!word ? <div className="cp-empty">כתבו שם, או לחצו על שם בתוך קובץ. מקבלים את ההגדרה ואת כל המקומות שמשתמשים בו, לפי קובץ, כדי לדעת מה עוד ישתנה.</div> : <>
          {defs.length > 0 && <div className="us-defs">
            <b>הגדרה</b>
            {defs.map((d) => (
              <div key={d[2] + d[3]} className="us-def">
                <span className="kind">{d[1]}</span>
                <button type="button" className="cp-gpath" onClick={() => openFile(d[2], d[3], d[3], word)}>{d[2]}:{d[3]}</button>
                <button type="button" className="cp-vs" onClick={() => openInVSCode(d[2], d[3])}>VS</button>
              </div>
            ))}
          </div>}
          {!code ? <div className="cp-empty">טוען קוד…</div> : result && <>
            <div className="cp-ginfo">{result.total} שורות ב־{result.nfiles} קבצים{result.nfiles > 1 ? " · שינוי בשם הזה נוגע בכל הקבצים האלה" : ""}</div>
            {result.files.map((f) => (
              <div key={f.path}>
                <div className="cp-gfile">
                  <button type="button" className="cp-gpath" onClick={() => openFile(f.path, f.hits[0].line, f.hits[0].line, word)}>{f.path}</button>
                  <span className="cnt">{f.hits.length}</span>{isTest(f.path) && <span className="t">טסט</span>}
                  <button type="button" className="cp-vs" onClick={() => openInVSCode(f.path, f.hits[0].line)}>VS</button>
                </div>
                {f.hits.map((h) => (
                  <div key={h.line} className={defKeys.has(f.path + ":" + h.line) ? "is-def" : ""}>
                    <GrepRow path={f.path} hit={h} term={word} />
                  </div>
                ))}
              </div>
            ))}
          </>}
        </>}
      </div>
    </div>
  );
}
