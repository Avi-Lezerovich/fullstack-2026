/* Quick find (Ctrl+K or /) over the guide, the recipes, the finder, code symbols and files,
   plus whatever the window adds (commands, env vars, endpoints). Port of palette.js. */
import { useEffect, useMemo, useRef, useState } from "react";
import { anchors, topics } from "./content";
import { files, indexStore, isTest } from "./code";
import { go } from "./nav";
import { openFile, openGrep, openPane, openUsages } from "./pane";
import { load, save, useStore } from "./store";
import { openInVSCode } from "./vscode";

export interface PalItem { type: string; title: string; sub?: string; keys?: string; test?: boolean; run: (alt?: boolean) => void }
interface Scored extends PalItem { nt: string; hay: string }

export const TYPES: Record<string, [label: string, weight: number]> = {
  finder: ["איפה זה?", 0], recipe: ["מתכון", 1], cmd: ["פקודה", 1], trouble: ["תקלה", 1], flow: ["endpoint", 1], env: ["משתנה", 1],
  guide: ["במדריך", 2], qa: ["שאלת מבחן", 3], code: ["בקוד", 2], file: ["קובץ", 4], grep: ["חיפוש בקוד", 5], go: ["מעבר", 0],
};
const LIMIT: Record<string, number> = { finder: 8, recipe: 5, cmd: 5, trouble: 4, flow: 5, env: 4, guide: 6, qa: 3, code: 8, file: 5, go: 4 };
const RECENT_KEY = "lolsuit-recent-v2", RECENT_MAX = 6;

export const norm = (s: string) => String(s || "").toLowerCase().replace(/[־_\-./:()"'`,]/g, " ").replace(/\s+/g, " ").trim();

function baseItems(): PalItem[] {
  const items: PalItem[] = [];
  topics.forEach((t) => items.push({ type: "guide", title: t.heading.replace(/<[^>]+>/g, ""), sub: "נושא " + t.num, run: () => go({ topic: t.id }) }));
  anchors.forEach((a) => items.push({ type: a.kind, title: a.title, sub: a.sub, keys: a.keys, run: () => go({ topic: a.topic, at: a.id }) }));
  indexStore.get().symbols.forEach((s) => items.push({
    type: "code", title: s[0], sub: `${s[2]}:${s[3]} · ${s[1]}`, keys: s[2], test: isTest(s[2]),
    run: (alt) => alt ? openInVSCode(s[2], s[3]) : openFile(s[2], s[3], s[3]),
  }));
  files().forEach((f) => items.push({ type: "file", title: f.split("/").pop()!, sub: f, keys: f, test: isTest(f), run: (alt) => alt ? openInVSCode(f) : openFile(f) }));
  return items;
}

export default function Palette({ extra = [], shortcuts = [] }: { extra?: PalItem[]; shortcuts?: PalItem[] }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const idx = useStore(indexStore);
  const all = useMemo<Scored[]>(() => (open ? [...extra, ...baseItems()] : []).map((it) => ({ ...it, nt: norm(it.title), hay: norm(it.title + " " + (it.sub || "") + " " + (it.keys || "")) })), [open, idx, extra]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /INPUT|TEXTAREA|SELECT/.test((document.activeElement || document.body).nodeName);
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); setOpen(true); }
      else if (e.key === "/" && !typing) { e.preventDefault(); setOpen(true); }
    };
    const onOpen = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("open-palette", onOpen);
    return () => { document.removeEventListener("keydown", onKey); window.removeEventListener("open-palette", onOpen); };
  }, []);
  useEffect(() => {
    const d = dlg.current!;
    if (open && !d.open) { d.showModal(); setQ(""); setSel(0); setTimeout(() => input.current?.focus(), 0); }
    if (!open && d.open) d.close();
  }, [open]);

  const [deb, setDeb] = useState("");
  useEffect(() => { const t = setTimeout(() => setDeb(q), 80); return () => clearTimeout(t); }, [q]);

  const shown = useMemo<PalItem[]>(() => {
    const raw = deb.trim(), nq = norm(raw), toks = nq.split(" ").filter(Boolean);
    if (!nq) {
      const recent = load<{ type: string; title: string; sub?: string }[]>(RECENT_KEY, [])
        .map((r) => all.find((it) => it.type === r.type && it.title === r.title && it.sub === r.sub))
        .filter(Boolean) as PalItem[];
      return [...recent.map((r) => ({ ...r, sub: "אחרון · " + (r.sub || "") })), ...shortcuts];
    }
    const scored: [number, Scored][] = [];
    for (const it of all) {
      if (!toks.every((t) => it.hay.includes(t))) continue;
      let s = (TYPES[it.type] || ["", 3])[1] * 10;
      if (it.nt === nq) s -= 40; else if (it.nt.startsWith(nq)) s -= 20; else if (it.nt.includes(nq)) s -= 12;
      else if (toks.every((t) => it.nt.includes(t))) s -= 6;
      if (it.test) s += 15;
      scored.push([s, it]);
    }
    scored.sort((a, b) => a[0] - b[0]);
    const per: Record<string, number> = {};
    const out: PalItem[] = [];
    for (const [, it] of scored) { per[it.type] = (per[it.type] || 0) + 1; if (per[it.type] <= (LIMIT[it.type] || 5)) out.push(it); }
    const word = raw.replace(/[^\w]/g, "");
    const tail: PalItem[] = [{ type: "grep", title: `חפש "${raw}" בכל הקוד`, sub: "כל המופעים, קובץ:שורה", run: () => openGrep(raw) }];
    if (word.length >= 3 && word === raw) tail.push({ type: "grep", title: `איפה משתמשים ב־${word}`, sub: "הגדרה וכל השימושים, לפי קובץ", run: () => openUsages(word) });
    return [...out.slice(0, 30), ...tail];
  }, [deb, all, shortcuts]);
  useEffect(() => setSel(0), [shown]);
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" }); }, [sel]);

  const choose = (i: number, alt = false) => {
    const it = shown[i];
    if (!it) return;
    setOpen(false);
    if (it.type !== "grep" && it.type !== "go") {
      const rec = { type: it.type, title: it.title, sub: (it.sub || "").replace(/^אחרון · /, "") };
      save(RECENT_KEY, [rec, ...load<typeof rec[]>(RECENT_KEY, []).filter((r) => !(r.type === rec.type && r.title === rec.title && r.sub === rec.sub))].slice(0, RECENT_MAX));
    }
    it.run(alt);
  };

  return (
    <dialog className="palette" ref={dlg} aria-label="חיפוש מהיר" onClose={() => setOpen(false)}
      onClick={(e) => { if (e.target === dlg.current) setOpen(false); }} onKeyDown={(e) => e.stopPropagation()}>
      <div className="pal-in">
        <span className="pal-ic" aria-hidden="true">⌕</span>
        <input ref={input} type="search" className="pal-q" placeholder="מה ביקשו לשנות? סיסמה, צבע, כפתור, endpoint, פקודה, PANEL_SIZE…" aria-label="חיפוש מהיר"
          autoComplete="off" spellCheck={false} value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => (s + 1) % Math.max(1, shown.length)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => (s - 1 + shown.length) % Math.max(1, shown.length)); }
            else if (e.key === "Enter") { e.preventDefault(); choose(q === deb ? sel : 0, e.altKey); }
          }} />
        <button className="btn" type="button" onClick={() => setOpen(false)}>Esc</button>
      </div>
      <div className="pal-list" role="listbox" ref={list}>
        {shown.map((it, i) => (
          <div key={i} className="pal-row" role="option" aria-selected={i === sel} onMouseMove={() => sel !== i && setSel(i)} onClick={(e) => choose(i, e.altKey)}>
            <span className={"pal-type t-" + it.type}>{(TYPES[it.type] || [it.type])[0]}</span>
            <span className="pal-main"><span className="pal-title">{it.title}</span><span className="pal-sub">{it.sub}</span></span>
          </div>
        ))}
      </div>
      <div className="pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd> בחירה</span><span><kbd>Enter</kbd> פתיחה</span><span><kbd>Alt</kbd>+<kbd>Enter</kbd> קוד/קובץ ישר ל־VS Code</span><span><kbd>Esc</kbd> סגירה</span></div>
    </dialog>
  );
}

export function paneShortcuts(): PalItem[] {
  return [
    { type: "file", title: "כל הקבצים", sub: "עץ הקבצים של הפרויקט", run: () => openPane("files") },
    { type: "grep", title: "חיפוש בכל הקוד", sub: "כמו grep -rn, בתוך הדפדפן", run: () => openPane("grep") },
    { type: "grep", title: "איפה משתמשים ב…", sub: "הגדרה וכל השימושים של שם", run: () => openPane("usages") },
  ];
}
