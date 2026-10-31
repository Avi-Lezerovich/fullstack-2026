/* Navigation between topics, anchors and the two windows.
   Each app registers how it shows a target; links inside topic HTML go through here. */
import { topicOfAnchor } from "./content";

export type Target = { topic: string; at?: string };
type Navigator = (t: Target) => void;
let current: Navigator = () => {};
export function setNavigator(fn: Navigator) { current = fn; }
export function go(t: Target) { current(t); }

/* data-reveal="r3" / "fx-12" / any anchor id */
export function goAnchor(id: string) {
  const topic = topicOfAnchor(id) || (/^r\d+$/.test(id) ? "t13" : "");
  if (topic) go({ topic, at: id });
}

/* ---------- two windows ---------- */
const STUDY = "index.html", EXAM = "exam.html";
function openNamed(url: string, name: string) {
  const w = window.open(url, name);
  if (w) w.focus();
}
export function openStudy(hash = "") { openNamed(STUDY + (hash ? "#" + hash : ""), "lolsuit-study"); }
export function openExam(hash = "") { openNamed(EXAM + (hash ? "#" + hash : ""), "lolsuit-exam"); }

/* Scroll an element into view, opening its <details> ancestors, and flash it. */
export function reveal(id: string, tries = 20) {
  const el = document.getElementById(id);
  if (!el) { if (tries > 0) setTimeout(() => reveal(id, tries - 1), 60); return; }
  for (let d = el.closest("details"); d; d = d.parentElement && d.parentElement.closest("details")) (d as HTMLDetailsElement).open = true;
  if (el instanceof HTMLDetailsElement) el.open = true;
  setTimeout(() => {
    el.scrollIntoView({ block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  }, 40);
}
