/* Diagrams inside topic HTML: sequence player, trial timeline, credential-chain simulator,
   zoom, and label backgrounds. Port of the old diagrams.js, scoped to one rendered root. */
import { SEQ } from "./seq";

export type SeqStep = [from: string, to: string, text: string, isReturn?: number] | { note: string; from: string; to: string };
export interface SeqSpec { actors: [id: string, label: string, role?: string][]; steps: SeqStep[] }

const NS = "http://www.w3.org/2000/svg";
function el(name: string, attrs: Record<string, string | number>, text?: string) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, String(attrs[k]));
  if (text != null) e.textContent = text;
  return e;
}
const $ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) => root.querySelector(sel) as T | null;
const $$ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) => Array.from(root.querySelectorAll(sel)) as T[];

function renderSeq(host: HTMLElement, spec: SeqSpec) {
  const colW = 150, padX = 20, top = 12, headH = 46, rowH = 34, selfH = 42, noteH = 30;
  const idx: Record<string, number> = {};
  spec.actors.forEach((a, i) => { idx[a[0]] = i; });
  const W = padX * 2 + colW * spec.actors.length + 140;
  let y = top + headH + 28;
  const rows: { kind: string; y: number; s: SeqStep }[] = [];
  spec.steps.forEach((s) => {
    if (!Array.isArray(s)) { rows.push({ kind: "note", y, s }); y += noteH + 10; }
    else if (s[0] === s[1]) { rows.push({ kind: "self", y, s }); y += selfH; }
    else { rows.push({ kind: "msg", y, s }); y += rowH; }
  });
  const H = y + 10;
  const fig = host.closest("figure");
  const cap = fig && $("figcaption", fig);
  const svg = el("svg", { class: "dg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cap ? cap.textContent || "" : "sequence diagram" }) as SVGSVGElement;
  svg.style.minWidth = "760px";
  const cx = (id: string) => padX + colW * idx[id] + colW / 2;
  spec.actors.forEach((a) => {
    const x = cx(a[0]), role = a[2] || "acc";
    svg.appendChild(el("line", { class: "life", x1: x, y1: top + headH, x2: x, y2: H - 6 }));
    svg.appendChild(el("rect", { class: "box " + role, x: x - colW / 2 + 8, y: top, width: colW - 16, height: headH, rx: 6 }));
    const label = a[1], sp = label.indexOf(" ");
    const parts = label.length > 18 && sp > 0 ? [label.slice(0, sp), label.slice(sp + 1)] : [label];
    parts.forEach((p, k) => svg.appendChild(el("text", { x, y: top + (parts.length === 1 ? 28 : 20 + k * 16), "text-anchor": "middle", class: k === 0 ? "b" : "sm" }, p)));
  });
  const steps: { g: SVGGElement; text: string }[] = [];
  rows.forEach((r) => {
    const g = el("g", { class: "step" }) as SVGGElement;
    svg.appendChild(g);
    if (r.kind === "note" && !Array.isArray(r.s)) {
      const n = r.s;
      const x1 = Math.min(cx(n.from), cx(n.to)) - colW / 2 + 12, x2 = Math.max(cx(n.from), cx(n.to)) + colW / 2 - 12;
      g.appendChild(el("rect", { class: "box gold dash", x: x1, y: r.y - 16, width: x2 - x1, height: noteH, rx: 6 }));
      g.appendChild(el("text", { x: (x1 + x2) / 2, y: r.y + 3, "text-anchor": "middle", class: "lbl" }, n.note));
      steps.push({ g, text: n.note });
      return;
    }
    const s = r.s as [string, string, string, number?];
    const ret = !!s[3];
    if (r.kind === "self") {
      const x = cx(s[0]);
      g.appendChild(el("path", { class: "ln", d: `M${x},${r.y - 6} h28 v18 h-26`, "marker-end": "url(#arw)" }));
      g.appendChild(el("text", { x: x + 34, y: r.y + 6, class: "lbl" }, s[2]));
    } else {
      const xa = cx(s[0]), xb = cx(s[1]), dir = xb > xa ? 1 : -1;
      g.appendChild(el("line", { class: "ln" + (ret ? " dash" : " acc"), x1: xa, y1: r.y, x2: xb - dir * 2, y2: r.y, "marker-end": ret ? "url(#arw)" : "url(#arwA)" }));
      g.appendChild(el("text", { x: (xa + xb) / 2, y: r.y - 6, "text-anchor": "middle", class: "lbl" }, s[2]));
    }
    const from = spec.actors[idx[s[0]]][1], to = spec.actors[idx[s[1]]][1];
    steps.push({ g, text: from + (s[0] === s[1] ? "" : (ret ? " ⇠ " : " → ") + to) + ": " + s[2] });
  });
  host.appendChild(svg);
  return steps;
}

function addPlayer(fig: HTMLElement, host: HTMLElement, steps: { g: SVGGElement; text: string }[]) {
  const tools = document.createElement("div");
  tools.className = "fig-tools";
  tools.innerHTML = '<button class="btn primary" type="button" data-a="next">צעד הבא ›</button>' +
    '<button class="btn" type="button" data-a="prev">‹ קודם</button>' +
    '<button class="btn" type="button" data-a="reset">הצג הכל</button>' +
    '<span class="step-text" aria-live="polite"></span>';
  let cur = -1;
  const out = $(".step-text", tools)!;
  const show = () => {
    host.classList.toggle("playing", cur >= 0);
    steps.forEach((s, i) => s.g.classList.toggle("cur", i === cur));
    out.textContent = cur >= 0 ? `${cur + 1}/${steps.length}  ${steps[cur].text}` : "";
  };
  tools.addEventListener("click", (e) => {
    const a = (e.target as Element).getAttribute("data-a");
    if (!a) return;
    if (a === "next") cur = Math.min(steps.length - 1, cur + 1);
    if (a === "prev") cur = Math.max(0, cur - 1);
    if (a === "reset") cur = -1;
    show();
  });
  fig.insertBefore(tools, $("figcaption", fig));
}

const SIM: Record<string, [string[], string]> = {
  ok: [["pre", "call", "ok"], "התשובה תקינה: note_success מאפס את ה־cooldown, נרשמת שורה ב־brain_calls, והטקסט עובר offline.tidy() לפני שחוזר לקורא."],
  rate: [["pre", "call", "rate", "next"], "429 עם PerMinute / throttling: is_rate_limit_error → המפתח נח 60 שניות (_RATE_COOLDOWN_SECONDS), והלולאה עוברת ל־credential הבא."],
  quota: [["pre", "call", "quota", "next"], "429 של מכסה (quota / resource_exhausted): is_quota_error → מושבת עד חצות UTC (_next_utc_midnight). אם יש cap=, ה־spent נקבע ל־cap."],
  other: [["pre", "call", "other", "next"], "כל שגיאה אחרת (400, timeout, DNS): מנוחה של 120 שניות (_TRANSIENT_COOLDOWN_SECONDS), ואז ה־credential הבא."],
  rpm: [["pre", "skip"], "rpm= מלא: chain.candidates() מדלג על המפתח עוד לפני הקריאה. אין המתנה ואין 429. ה־credential הבא בשרשרת מקבל את הבקשה."],
  all: [["pre", "call", "rate", "quota", "other", "fallback", "offline"], "כל ה־credentials נכשלו: AllCredentialsFailed נתפס ב־brain.generate → offline.generate(). (invent_lawsuit עם require_llm=True מחזיר None, ו־remember() מחזיר None.)"],
  offline: [["offline", "nollm"], "BRAIN_FORCE_OFFLINE=1 או אין credential שמיש: settings.use_llm הוא False → offline.generate() ישירות, בלי רשת. זו ברירת המחדל ב־docker compose."],
};

export function labelBackgrounds(scope: ParentNode) {
  $$<SVGTextElement>("svg.dg text.lbl", scope).forEach((t) => {
    if (t.dataset.bg) return;
    try {
      const b = t.getBBox();
      if (!b.width) return;
      t.parentNode!.insertBefore(el("rect", { class: "lblbg", x: b.x - 3, y: b.y - 1, width: b.width + 6, height: b.height + 2, rx: 3 }), t);
      t.dataset.bg = "1";
    } catch { /* not laid out */ }
  });
}

/* Wire every diagram inside root. `zoom` shows a cloned svg in a dialog. */
export function enhanceDiagrams(root: HTMLElement, zoom: (svg: SVGSVGElement, title: string) => void) {
  $$(".seq[data-seq]", root).forEach((host) => {
    const spec = SEQ[host.dataset.seq || ""];
    if (!spec || host.querySelector("svg")) return;
    const steps = renderSeq(host, spec);
    const fig = host.closest("figure") as HTMLElement | null;
    if (fig) addPlayer(fig, host, steps);
  });

  const tl = $("#trialTimeline", root);
  if (tl && !tl.dataset.wired) {
    tl.dataset.wired = "1";
    const dayLabels = $$<SVGTextElement>("g.days text", tl);
    const fmt = (min: number) => min === 0 ? "0" : min % 1440 === 0 ? min / 1440 + "d" : min % 60 === 0 ? min / 60 + "h" : min + "m";
    const setPhase = (pm: number) => {
      dayLabels.forEach((t, d) => { t.textContent = `day ${d} · ${fmt(d * pm)}`; });
      const out = $("#phaseOut", root);
      if (out) out.textContent = `PHASE_MINUTES=${pm} → כל המשפט (7 ימים) נמשך ` + fmt(7 * pm).replace("d", " ימים").replace("h", " שעות").replace("m", " דקות");
      $$("#phaseSeg button", root).forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.pm) === pm)));
    };
    $$("#phaseSeg button", root).forEach((b) => b.addEventListener("click", () => setPhase(Number(b.dataset.pm))));
    setPhase(1440);
  }

  const simFig = $("#chainSim", root);
  if (simFig && !simFig.dataset.wired) {
    simFig.dataset.wired = "1";
    const simOut = $(".sim-out", simFig);
    $$("#simSeg button", simFig).forEach((b) => b.addEventListener("click", () => {
      const key = b.dataset.sim || "", on = b.getAttribute("aria-pressed") !== "true";
      $$("#simSeg button", simFig).forEach((x) => x.setAttribute("aria-pressed", "false"));
      simFig.classList.toggle("sim-on", on);
      $$(".branch", simFig).forEach((g) => g.classList.remove("hit"));
      if (on && SIM[key]) {
        b.setAttribute("aria-pressed", "true");
        SIM[key][0].forEach((name) => $$(`.branch[data-b="${name}"]`, simFig).forEach((g) => g.classList.add("hit")));
        if (simOut) simOut.textContent = SIM[key][1];
      } else if (simOut) simOut.textContent = "בחרו תרחיש כדי לראות לאן הקריאה הולכת.";
    }));
  }

  $$("figure", root).forEach((fig) => {
    if (!($("svg.dg", fig) || $(".seq", fig)) || $("[data-zoom]", fig)) return;
    let tools = $(".fig-tools", fig);
    if (!tools) { tools = document.createElement("div"); tools.className = "fig-tools"; fig.insertBefore(tools, $("figcaption", fig)); }
    const z = document.createElement("button");
    z.className = "btn"; z.type = "button"; z.textContent = "הגדל"; z.dataset.zoom = "1";
    z.addEventListener("click", () => {
      const src = $<SVGSVGElement>("svg.dg", fig);
      const cap = $("figcaption", fig);
      if (src) zoom(src, cap && cap.textContent ? cap.textContent.slice(0, 90) + "…" : "");
    });
    tools.appendChild(z);
  });

  labelBackgrounds(root);
  $$<HTMLDetailsElement>("details", root).forEach((d) => {
    if (d.dataset.wired) return;
    d.dataset.wired = "1";
    d.addEventListener("toggle", () => { if (d.open) labelBackgrounds(d); });
  });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => {
    $$("svg.dg rect.lblbg", root).forEach((r) => r.remove());
    $$<SVGTextElement>("svg.dg text.lbl", root).forEach((t) => { delete t.dataset.bg; });
    labelBackgrounds(root);
  });
}
