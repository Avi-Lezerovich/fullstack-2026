/* The files a task touches, as buttons: open in the pane, open in VS Code, or all at once (tool 3). */
import { useStore } from "../shared/store";
import { indexStore, resolvePath, type Ref } from "../shared/code";
import { parseRef } from "../shared/content";
import { openFile } from "../shared/pane";
import { openAllInVSCode, openInVSCode } from "../shared/vscode";

export function resolveRefs(refs: string[]): Ref[] {
  const out: Ref[] = [];
  const seen = new Set<string>();
  for (const r of refs) {
    const { path, line } = parseRef(r);
    const p = resolvePath(path);
    if (!p) continue;
    const k = p + ":" + line;
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ path: p, line });
  }
  return out;
}

/* one entry per file (first line mentioned), for "open all" */
export function perFile(refs: Ref[]): Ref[] {
  const m = new Map<string, Ref>();
  refs.forEach((r) => { if (!m.has(r.path)) m.set(r.path, r); });
  return [...m.values()];
}

export function OpenAllButton({ refs, label }: { refs: string[]; label?: string }) {
  useStore(indexStore);
  const files = perFile(resolveRefs(refs));
  if (!files.length) return null;
  return (
    <button className="btn vs-all" type="button" title={files.map((f) => f.path + (f.line ? ":" + f.line : "")).join("\n")}
      onClick={() => openAllInVSCode(files)}>
      {label || `פתח ${files.length} ${files.length === 1 ? "קובץ" : "קבצים"} ב־VS Code`}
    </button>
  );
}

export function RefList({ refs }: { refs: string[] }) {
  useStore(indexStore);
  const list = resolveRefs(refs);
  if (!list.length) return null;
  return (
    <ul className="reflist">
      {list.map((r) => (
        <li key={r.path + r.line}>
          <button type="button" className="ref" onClick={() => openFile(r.path, r.line)}><code>{r.path}{r.line ? ":" + r.line : ""}</code></button>
          <button type="button" className="cp-vs" title="פתח ב־VS Code" onClick={() => openInVSCode(r.path, r.line)}>VS</button>
        </li>
      ))}
    </ul>
  );
}
