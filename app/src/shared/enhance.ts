/* Behaviour for topic HTML once it is in the DOM: copy buttons on code blocks, links from
   every file/symbol mention into the code, and the data-* actions. Ports of the matching
   parts of core.js and code-viewer.js. Returns a cleanup function. */
import { defOf, indexStore, resolvePath } from "./code";
import { goAnchor, go } from "./nav";
import { openFile, openGrep, openPane } from "./pane";
import { openInVSCode } from "./vscode";
import { enhanceDiagrams } from "./diagrams";
import { copy } from "./toast";

const PATH_RX = /^([\w./-]+\.(?:py|tsx?|sql|ya?ml|template|sh|md|txt|ini|json|html)|Makefile|\.env\.example)(?::(\d+)(?:[–-](\d+))?)?$/;
const SYM_RX = /^@?([A-Za-z_][\w.]*)(?:\(\))?$/;

export function copyBoxes(root: HTMLElement) {
  root.querySelectorAll("pre").forEach((pre) => {
    if (pre.parentElement?.classList.contains("codebox")) return;
    const box = document.createElement("div");
    box.className = "codebox";
    pre.parentNode!.insertBefore(box, pre);
    box.appendChild(pre);
    const b = document.createElement("button");
    b.className = "copy"; b.type = "button"; b.textContent = "העתק";
    b.addEventListener("click", () => {
      // copy without the guide's own annotations (span.c), which would break a pasted command
      const clone = pre.cloneNode(true) as HTMLElement;
      clone.querySelectorAll(".c").forEach((n) => n.remove());
      const text = (clone.textContent || "").split("\n").map((l) => l.replace(/\s+$/, "")).join("\n").trim();
      copy(text, "הפקודה");
      b.textContent = "הועתק"; setTimeout(() => { b.textContent = "העתק"; }, 1400);
    });
    box.appendChild(b);
  });
}

export function linkCode(root: HTMLElement) {
  const files = indexStore.get().files;
  let last: { path: string; block: Element | null } | null = null;
  root.querySelectorAll("code").forEach((c) => {
    if (c.closest("pre") || c.classList.contains("codelink")) return;
    const t = (c.textContent || "").trim();
    const block = c.closest(".fx, li, p, td");
    let ref: { path: string; line: number; end: number } | null = null;
    let m = PATH_RX.exec(t);
    if (m) {
      const f = resolvePath(m[1]);
      if (f) { ref = { path: f, line: Number(m[2] || 0), end: Number(m[3] || 0) }; last = { path: f, block }; }
    } else if ((m = /^:(\d+)$/.exec(t)) && last && last.block === block) {
      ref = { path: last.path, line: Number(m[1]), end: 0 };
    } else if ((m = SYM_RX.exec(t)) && t.length >= 4) {
      const name = m[1].split(".").pop()!;
      const d = name.length >= 4 ? defOf(name) : null;
      if (d) ref = { path: d[2], line: d[3], end: 0 };
    }
    if (!ref || ref.line > (files[ref.path] || 0)) return;
    c.classList.add("codelink");
    c.tabIndex = 0;
    c.setAttribute("role", "link");
    c.dataset.path = ref.path; c.dataset.line = String(ref.line); c.dataset.end = String(ref.end);
    c.title = "לחיצה: פתח בקוד · Alt+לחיצה: פתח ב־VS Code · " + ref.path + (ref.line ? ":" + ref.line : "");
  });
}

/* One delegated handler for everything clickable inside topic HTML. */
export function bindActions(root: HTMLElement) {
  const onClick = (e: MouseEvent) => {
    const t = e.target as HTMLElement;
    const c = t.closest("code.codelink") as HTMLElement | null;
    if (c) {
      e.preventDefault();
      const path = c.dataset.path!, line = Number(c.dataset.line), end = Number(c.dataset.end);
      if (e.altKey) openInVSCode(path, line); else openFile(path, line, end);
      return;
    }
    const g = t.closest("[data-grep]") as HTMLElement | null;
    if (g) { e.preventDefault(); openGrep(g.dataset.grep || ""); return; }
    const r = t.closest("[data-reveal]") as HTMLElement | null;
    if (r) { e.preventDefault(); goAnchor(r.dataset.reveal!); return; }
    const goEl = t.closest("[data-go]") as HTMLElement | null;
    if (goEl) { e.preventDefault(); go({ topic: goEl.dataset.go! }); return; }
    const oc = t.closest("[data-open-code]") as HTMLElement | null;
    if (oc) { e.preventDefault(); openPane((oc.dataset.openCode as "files" | "grep") || "files"); return; }
    const op = t.closest("[data-open-palette]");
    if (op) { e.preventDefault(); window.dispatchEvent(new CustomEvent("open-palette")); }
  };
  const onKey = (e: KeyboardEvent) => {
    const t = e.target as HTMLElement;
    if (e.key === "Enter" && t.classList.contains("codelink")) openFile(t.dataset.path!, Number(t.dataset.line), Number(t.dataset.end));
  };
  root.addEventListener("click", onClick);
  root.addEventListener("keydown", onKey);
  return () => { root.removeEventListener("click", onClick); root.removeEventListener("keydown", onKey); };
}

export function enhance(root: HTMLElement, zoom: (svg: SVGSVGElement, title: string) => void) {
  copyBoxes(root);
  linkCode(root);
  enhanceDiagrams(root, zoom);
  return bindActions(root);
}
