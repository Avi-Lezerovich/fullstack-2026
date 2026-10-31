/* Open files in the local VS Code: vscode://file/<absolute path>:<line>:<column>. */
import type { Ref } from "./code";
import { toast } from "./toast";

export const LOCAL_ROOT = "C:/Users/lzr/Documents/GitHub/fullstack-2026"; // the exam laptop's checkout

export function vscodeUrl(path: string, line?: number) {
  return "vscode://file/" + encodeURI(LOCAL_ROOT + "/" + path) + (line ? `:${line}:1` : "");
}

export function openInVSCode(path: string, line?: number) {
  window.location.href = vscodeUrl(path, line);
}

/* Several files, one after another: VS Code opens each as a tab. The browser may ask
   once whether to allow vscode:// links; after "always allow" the rest go through. */
export function openAllInVSCode(refs: Ref[], gapMs = 700) {
  const seen = new Set<string>();
  const list = refs.filter((r) => { const k = r.path + ":" + (r.line || 0); if (seen.has(k)) return false; seen.add(k); return true; });
  list.forEach((r, i) => setTimeout(() => openInVSCode(r.path, r.line), i * gapMs));
  toast(`פותח ${list.length} קבצים ב־VS Code`);
  return list;
}
