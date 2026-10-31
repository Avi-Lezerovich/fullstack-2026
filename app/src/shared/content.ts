/* Topics from virtual:topics, prepared once: every searchable element gets a stable id
   (so the palette and links can jump to it), and the exam window's structured views —
   finder items, recipes, troubleshooting rows, Q&A — are read out of the same HTML. */
import rawTopics from "virtual:topics";
import type { Topic } from "../../plugins/content";

export type { Topic };
export interface Anchor { topic: string; id: string; title: string; sub: string; keys: string; kind: "guide" | "qa" | "recipe" | "finder" }
export interface FinderItem { id: string; q: string; keys: string; html: string; refs: string[] }
export interface FinderGroup { title: string; layer: string; items: FinderItem[] }
export interface Recipe { id: string; num: number; level: "easy" | "med" | "hard"; title: string; titleHtml: string; html: string; refs: string[]; verifyHtml: string }
export interface TroubleRow { id: string; section: string; symptom: string; symptomHtml: string; causeHtml: string; fixHtml: string }

const SEARCHABLE = "details.sub > summary, h3, h4, .card > h4, dt, .gl-term, details.qa, details.recipe, .fx";
const txt = (el: Element | null) => (el ? (el.textContent || "").replace(/\s+/g, " ").trim() : "");
const CODE_PATH = /^([\w./-]+\.(?:py|tsx?|sql|ya?ml|template|sh|md|txt|ini|json|html)|Makefile|\.env\.example)(?::(\d+)(?:[–-](\d+))?)?$/;

function prepare(t: Topic) {
  const tpl = document.createElement("template");
  tpl.innerHTML = t.html;
  const anchors: Anchor[] = [];
  let n = 0;
  tpl.content.querySelectorAll(SEARCHABLE).forEach((node) => {
    const host = node.nodeName === "SUMMARY" ? node.parentElement! : node;
    if (!host.id) host.id = node.matches(".fx") ? `fx-${n++}` : `a-${t.id}-${n++}`;
    if (host.closest(".fx") && !host.matches(".fx")) return;
    if (host.matches("details.qa")) anchors.push({ topic: t.id, id: host.id, kind: "qa", title: txt(host.querySelector("summary")), sub: t.title, keys: "" });
    else if (host.matches("details.recipe")) anchors.push({ topic: t.id, id: host.id, kind: "recipe", title: txt(host.querySelector("summary")).replace(/^(קל|בינוני|מתקדם)\s*/, ""), sub: "מתכון", keys: txt(host).slice(0, 1500) });
    else if (host.matches(".fx")) anchors.push({ topic: t.id, id: host.id, kind: "finder", title: txt(host.querySelector(".fx-q")), sub: txt(host.querySelector(".fx-where")), keys: ((host as HTMLElement).dataset.keys || "") + " " + txt(host) });
    else anchors.push({ topic: t.id, id: host.id, kind: "guide", title: txt(node), sub: t.title, keys: node.nodeName === "DT" && node.nextElementSibling ? txt(node.nextElementSibling) : "" });
  });
  return { html: tpl.innerHTML, anchors, frag: tpl.content };
}

/* Every `<code>path[:line]</code>` inside an element, in order, deduped. */
function refsIn(root: ParentNode): string[] {
  const out: string[] = [];
  let last = "";
  root.querySelectorAll("code").forEach((c) => {
    if (c.closest("pre")) return;
    const t = (c.textContent || "").trim();
    const m = CODE_PATH.exec(t);
    if (m) { last = m[1]; out.push(m[2] ? `${m[1]}:${m[2]}` : m[1]); }
    else if (/^:\d+$/.test(t) && last) out.push(last + t);
  });
  return [...new Set(out)];
}

const prepared = rawTopics.map((t) => ({ topic: t, ...prepare(t) }));

export const topics: Topic[] = prepared.map((p) => ({ ...p.topic, html: p.html }));
export const anchors: Anchor[] = prepared.flatMap((p) => p.anchors);
export const topicById = (id: string) => topics.find((t) => t.id === id);
export const topicOfAnchor = (id: string) => anchors.find((a) => a.id === id)?.topic;

function fragOf(id: string) { return prepared.find((p) => p.topic.id === id)?.frag; }

export const finderGroups: FinderGroup[] = (() => {
  const frag = fragOf("t0");
  if (!frag) return [];
  return Array.from(frag.querySelectorAll(".fx-group")).map((g) => {
    const h3 = g.querySelector("h3");
    const layer = txt(h3?.querySelector(".lyr") || null);
    return {
      title: txt(h3).replace(layer, "").trim(), layer,
      items: Array.from(g.querySelectorAll(".fx")).map((fx) => {
        const body = fx.cloneNode(true) as HTMLElement;
        body.querySelector(".fx-q")?.remove();
        return { id: fx.id, q: txt(fx.querySelector(".fx-q")), keys: ((fx as HTMLElement).dataset.keys || "") + " " + txt(fx), html: body.innerHTML, refs: refsIn(fx) };
      }),
    };
  });
})();

/* t0's intro: everything before the finder groups (cards for exam day). */
export const finderIntroHtml: string = (() => {
  const frag = fragOf("t0");
  if (!frag) return "";
  const wrap = document.createElement("div");
  frag.querySelectorAll(".exam-day").forEach((n) => wrap.appendChild(n.cloneNode(true)));
  return wrap.innerHTML;
})();

export const recipes: Recipe[] = (() => {
  const frag = fragOf("t13");
  if (!frag) return [];
  return Array.from(frag.querySelectorAll("details.recipe")).map((d) => {
    const summary = d.querySelector("summary")!.cloneNode(true) as HTMLElement;
    const tag = summary.querySelector(".tag");
    const level = (tag?.classList.contains("hard") ? "hard" : tag?.classList.contains("med") ? "med" : "easy") as Recipe["level"];
    tag?.remove();
    const titleHtml = summary.innerHTML.trim().replace(/^\d+\.\s*/, "");
    const inner = d.querySelector(".in") as HTMLElement;
    // the "אימות" block: from that label to the next label
    let verifyHtml = "";
    const labels = Array.from(inner.querySelectorAll(".rlabel"));
    const v = labels.find((l) => /אימות|בדיקה/.test(l.textContent || ""));
    if (v) {
      for (let n = v.nextElementSibling; n && !n.classList.contains("rlabel"); n = n.nextElementSibling) verifyHtml += n.outerHTML;
    }
    return {
      id: d.id, num: Number(d.id.replace(/^r/, "")), level, title: txt(summary).replace(/^\d+\.\s*/, ""), titleHtml,
      html: inner.innerHTML, refs: refsIn(inner), verifyHtml,
    };
  });
})();

export const cookbookIntroHtml: string = (() => {
  const frag = fragOf("t13");
  const c = frag?.querySelector(".callout.exam");
  return c ? c.outerHTML : "";
})();

export const troubleRows: TroubleRow[] = (() => {
  const frag = fragOf("t19");
  if (!frag) return [];
  const out: TroubleRow[] = [];
  let section = "";
  let k = 0;
  frag.childNodes.forEach((n) => {
    if (!(n instanceof HTMLElement)) return;
    if (n.tagName === "H3") section = txt(n);
    if (n.classList.contains("ts")) n.querySelectorAll(".ts-row").forEach((row) => {
      const s = row.querySelector(".ts-s")!, c = row.querySelector(".ts-c"), f = row.querySelector(".ts-f");
      out.push({ id: `ts-${k++}`, section, symptom: txt(s), symptomHtml: s.innerHTML, causeHtml: c?.innerHTML || "", fixHtml: f?.innerHTML || "" });
    });
  });
  return out;
})();

/* What's left of t19 after the rows (the git "go back" block and the first-check callout). */
export const troubleExtrasHtml: string = (() => {
  const frag = fragOf("t19");
  if (!frag) return "";
  const wrap = document.createElement("div");
  const first = frag.querySelector(".callout.key");
  if (first) wrap.appendChild(first.cloneNode(true));
  return wrap.innerHTML;
})();

export const cheatHtml: string = (() => {
  const frag = fragOf("t16");
  if (!frag) return "";
  const wrap = document.createElement("div");
  frag.childNodes.forEach((n) => wrap.appendChild(n.cloneNode(true)));
  return wrap.innerHTML;
})();

export function parseRef(ref: string): { path: string; line: number } {
  const m = /^(.*?)(?::(\d+))?$/.exec(ref)!;
  return { path: m[1], line: Number(m[2] || 0) };
}
