/* LolSuit study guide — diagrams: sequence player, trial timeline, credential-chain
   simulator, zoom dialog and label backgrounds. Runs before core.js. */
(function () {
  "use strict";
  var Guide = window.Guide = window.Guide || {};
  var NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---------- sequence diagrams: hand-written data → inline SVG ---------- */
  var SEQ = window.GUIDE_SEQ || {};
  function renderSeq(host, spec) {
    var colW = 150, padX = 20, top = 12, headH = 46, rowH = 34, selfH = 42, noteH = 30;
    var idx = {};
    spec.actors.forEach(function (a, i) { idx[a[0]] = i; });
    var W = padX * 2 + colW * spec.actors.length + 140;
    var y = top + headH + 28, rows = [];
    spec.steps.forEach(function (s) {
      if (!Array.isArray(s)) { rows.push({ kind: "note", y: y, s: s }); y += noteH + 10; }
      else if (s[0] === s[1]) { rows.push({ kind: "self", y: y, s: s }); y += selfH; }
      else { rows.push({ kind: "msg", y: y, s: s }); y += rowH; }
    });
    var H = y + 10;
    var fig = host.closest("figure");
    var svg = el("svg", { "class": "dg", viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": fig && $("figcaption", fig) ? $("figcaption", fig).textContent : "sequence diagram" });
    svg.style.minWidth = "760px";
    function cx(id) { return padX + colW * idx[id] + colW / 2; }
    spec.actors.forEach(function (a) {
      var x = cx(a[0]), role = a[2] || "acc";
      svg.appendChild(el("line", { "class": "life", x1: x, y1: top + headH, x2: x, y2: H - 6 }));
      svg.appendChild(el("rect", { "class": "box " + role, x: x - colW / 2 + 8, y: top, width: colW - 16, height: headH, rx: 6 }));
      var label = a[1], sp = label.indexOf(" ");
      var parts = label.length > 18 && sp > 0 ? [label.slice(0, sp), label.slice(sp + 1)] : [label];
      parts.forEach(function (p, k) {
        svg.appendChild(el("text", { x: x, y: top + (parts.length === 1 ? 28 : 20 + k * 16), "text-anchor": "middle", "class": k === 0 ? "b" : "sm" }, p));
      });
    });
    var steps = [];
    rows.forEach(function (r) {
      var g = el("g", { "class": "step" });
      svg.appendChild(g);
      if (r.kind === "note") {
        var x1 = Math.min(cx(r.s.from), cx(r.s.to)) - colW / 2 + 12, x2 = Math.max(cx(r.s.from), cx(r.s.to)) + colW / 2 - 12;
        g.appendChild(el("rect", { "class": "box gold dash", x: x1, y: r.y - 16, width: x2 - x1, height: noteH, rx: 6 }));
        g.appendChild(el("text", { x: (x1 + x2) / 2, y: r.y + 3, "text-anchor": "middle", "class": "lbl" }, r.s.note));
        steps.push({ g: g, text: r.s.note });
        return;
      }
      var s = r.s, ret = !!s[3];
      if (r.kind === "self") {
        var x = cx(s[0]);
        g.appendChild(el("path", { "class": "ln", d: "M" + x + "," + (r.y - 6) + " h28 v18 h-26", "marker-end": "url(#arw)" }));
        g.appendChild(el("text", { x: x + 34, y: r.y + 6, "class": "lbl" }, s[2]));
      } else {
        var xa = cx(s[0]), xb = cx(s[1]), dir = xb > xa ? 1 : -1;
        g.appendChild(el("line", { "class": "ln" + (ret ? " dash" : " acc"), x1: xa, y1: r.y, x2: xb - dir * 2, y2: r.y, "marker-end": ret ? "url(#arw)" : "url(#arwA)" }));
        g.appendChild(el("text", { x: (xa + xb) / 2, y: r.y - 6, "text-anchor": "middle", "class": "lbl" }, s[2]));
      }
      var from = spec.actors[idx[s[0]]][1], to = spec.actors[idx[s[1]]][1];
      steps.push({ g: g, text: from + (s[0] === s[1] ? "" : (ret ? " ⇠ " : " → ") + to) + ": " + s[2] });
    });
    host.appendChild(svg);
    return steps;
  }
  function addPlayer(fig, host, steps) {
    var tools = document.createElement("div"); tools.className = "fig-tools";
    tools.innerHTML = '<button class="btn primary" type="button" data-a="next">צעד הבא ›</button>' +
      '<button class="btn" type="button" data-a="prev">‹ קודם</button>' +
      '<button class="btn" type="button" data-a="reset">הצג הכל</button>' +
      '<span class="step-text" aria-live="polite"></span>';
    var cur = -1, out = $(".step-text", tools);
    function show() {
      host.classList.toggle("playing", cur >= 0);
      steps.forEach(function (s, i) { s.g.classList.toggle("cur", i === cur); });
      out.textContent = cur >= 0 ? (cur + 1) + "/" + steps.length + "  " + steps[cur].text : "";
    }
    tools.addEventListener("click", function (e) {
      var a = e.target.getAttribute && e.target.getAttribute("data-a");
      if (!a) return;
      if (a === "next") cur = Math.min(steps.length - 1, cur + 1);
      if (a === "prev") cur = Math.max(0, cur - 1);
      if (a === "reset") cur = -1;
      show();
    });
    var cap = $("figcaption", fig);
    fig.insertBefore(tools, cap);
  }
  $$(".seq[data-seq]").forEach(function (host) {
    var spec = SEQ[host.dataset.seq];
    if (!spec) return;
    var steps = renderSeq(host, spec);
    addPlayer(host.closest("figure"), host, steps);
  });

  /* ---------- trial timeline: what a "day" means at a given PHASE_MINUTES ---------- */
  var tl = $("#trialTimeline");
  if (tl) {
    var dayLabels = $$("g.days text", tl);
    function fmt(min) {
      if (min === 0) return "0";
      if (min % 1440 === 0) return (min / 1440) + "d";
      if (min % 60 === 0) return (min / 60) + "h";
      return min + "m";
    }
    function setPhase(pm) {
      dayLabels.forEach(function (t, d) { t.textContent = "day " + d + " · " + fmt(d * pm); });
      $("#phaseOut").textContent = "PHASE_MINUTES=" + pm + " → כל המשפט (7 ימים) נמשך " + fmt(7 * pm).replace("d", " ימים").replace("h", " שעות").replace("m", " דקות");
      $$("#phaseSeg button").forEach(function (b) { b.setAttribute("aria-pressed", String(Number(b.dataset.pm) === pm)); });
    }
    $$("#phaseSeg button").forEach(function (b) { b.addEventListener("click", function () { setPhase(Number(b.dataset.pm)); }); });
    setPhase(1440);
  }

  /* ---------- credential-chain simulator ---------- */
  var SIM = {
    ok:      [["pre", "call", "ok"], "התשובה תקינה: note_success מאפס את ה־cooldown, נרשמת שורה ב־brain_calls, והטקסט עובר offline.tidy() לפני שחוזר לקורא."],
    rate:    [["pre", "call", "rate", "next"], "429 עם PerMinute / throttling: is_rate_limit_error → המפתח נח 60 שניות (_RATE_COOLDOWN_SECONDS), והלולאה עוברת ל־credential הבא."],
    quota:   [["pre", "call", "quota", "next"], "429 של מכסה (quota / resource_exhausted): is_quota_error → מושבת עד חצות UTC (_next_utc_midnight). אם יש cap=, ה־spent נקבע ל־cap."],
    other:   [["pre", "call", "other", "next"], "כל שגיאה אחרת (400, timeout, DNS): מנוחה של 120 שניות (_TRANSIENT_COOLDOWN_SECONDS), ואז ה־credential הבא."],
    rpm:     [["pre", "skip"], "rpm= מלא: chain.candidates() מדלג על המפתח עוד לפני הקריאה. אין המתנה ואין 429. ה־credential הבא בשרשרת מקבל את הבקשה."],
    all:     [["pre", "call", "rate", "quota", "other", "fallback", "offline"], "כל ה־credentials נכשלו: AllCredentialsFailed נתפס ב־brain.generate → offline.generate(). (invent_lawsuit עם require_llm=True מחזיר None, ו־remember() מחזיר None.)"],
    offline: [["offline", "nollm"], "BRAIN_FORCE_OFFLINE=1 או אין credential שמיש: settings.use_llm הוא False → offline.generate() ישירות, בלי רשת. זו ברירת המחדל ב־docker compose."]
  };
  var simFig = $("#chainSim");
  if (simFig) {
    var simOut = $(".sim-out", simFig);
    $$("#simSeg button", simFig).forEach(function (b) {
      b.addEventListener("click", function () {
        var key = b.dataset.sim, on = b.getAttribute("aria-pressed") !== "true";
        $$("#simSeg button", simFig).forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
        simFig.classList.toggle("sim-on", on);
        $$(".branch", simFig).forEach(function (g) { g.classList.remove("hit"); });
        if (on) {
          b.setAttribute("aria-pressed", "true");
          SIM[key][0].forEach(function (name) { $$('.branch[data-b="' + name + '"]', simFig).forEach(function (g) { g.classList.add("hit"); }); });
          simOut.textContent = SIM[key][1];
        } else simOut.textContent = "בחרו תרחיש כדי לראות לאן הקריאה הולכת.";
      });
    });
  }

  /* ---------- zoom any diagram ---------- */
  var dlg = $("#zoomDlg");
  $$("main figure").forEach(function (fig) {
    var svg = $("svg.dg", fig) || $(".seq", fig);
    if (!svg) return;
    var tools = $(".fig-tools", fig);
    if (!tools) { tools = document.createElement("div"); tools.className = "fig-tools"; fig.insertBefore(tools, $("figcaption", fig)); }
    var z = document.createElement("button"); z.className = "btn"; z.type = "button"; z.textContent = "הגדל";
    z.addEventListener("click", function () {
      var src = $("svg.dg", fig);
      var body = $(".zbody", dlg); body.innerHTML = "";
      body.appendChild(src.cloneNode(true));
      $(".ztitle", dlg).textContent = ($("figcaption", fig) || {}).textContent ? $("figcaption", fig).textContent.slice(0, 90) + "…" : "";
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    });
    tools.appendChild(z);
  });
  $("#zoomClose").addEventListener("click", function () { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg && dlg.close) dlg.close(); });

  /* ---------- label backgrounds (needs layout, so per visible scope) ---------- */
  function labelBackgrounds(scope) {
    $$("svg.dg text.lbl", scope).forEach(function (t) {
      if (t.dataset.bg) return;
      try {
        var b = t.getBBox();
        if (!b.width) return;
        t.parentNode.insertBefore(el("rect", { "class": "lblbg", x: b.x - 3, y: b.y - 1, width: b.width + 6, height: b.height + 2, rx: 3 }), t);
        t.dataset.bg = "1";
      } catch (e) { /* not laid out */ }
    });
  }
  Guide.labelBackgrounds = labelBackgrounds;
  labelBackgrounds(document);
  $$("main details").forEach(function (d) { d.addEventListener("toggle", function () { if (d.open) labelBackgrounds(d); }); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () {
    $$("svg.dg rect.lblbg").forEach(function (r) { r.remove(); });
    $$("svg.dg text.lbl").forEach(function (t) { delete t.dataset.bg; });
    labelBackgrounds(document);
  });

})();
