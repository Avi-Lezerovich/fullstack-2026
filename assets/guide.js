/* LolSuit study guide — page behaviour. No dependencies. */
(function () {
  "use strict";
  var STORE = "lolsuit-study-v2";
  function load() { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch (e) { return {}; } }
  function save() { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { /* storage blocked */ } }
  var state = load();
  state.done = state.done || {};
  var NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---------- theme ---------- */
  var root = document.documentElement;
  if (state.theme === "dark" || state.theme === "light") root.setAttribute("data-theme", state.theme);
  $("#themeBtn").addEventListener("click", function () {
    var current = root.getAttribute("data-theme") ||
      (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    var next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    state.theme = next; save();
  });

  /* ---------- TOC + progress (progress reads as the trial's own phases) ---------- */
  var sections = $$("section.topic");
  var toc = $("#toc");
  sections.forEach(function (sec, i) {
    var li = document.createElement("li");
    li.dataset.target = sec.id;
    var a = document.createElement("a");
    a.href = "#" + sec.id;
    a.innerHTML = '<span class="num"></span><span></span><span class="chk" aria-hidden="true">✔</span>';
    a.children[0].textContent = String(i + 1).padStart(2, "0");
    a.children[1].textContent = sec.dataset.title;
    a.addEventListener("click", function () { sec.classList.remove("collapsed"); document.body.classList.remove("menu-open"); });
    li.appendChild(a);
    toc.appendChild(li);
  });
  var PHASES = [
    ["filed", "הוגשה"], ["witness_phase", "איסוף עדויות"], ["jury_deliberation", "דיוני מושבעים"],
    ["verdict_reached", "ניתן פסק דין"], ["closed", "התיק נסגר"]
  ];
  function phaseIndex(n, total) {
    if (n >= total) return 4;
    return Math.min(3, Math.floor(n / (total / 4)));
  }
  function refreshProgress() {
    var n = 0;
    sections.forEach(function (sec) {
      var done = !!state.done[sec.id];
      if (done) n++;
      var li = toc.querySelector('li[data-target="' + sec.id + '"]');
      if (li) li.classList.toggle("done", done);
    });
    var p = phaseIndex(n, sections.length);
    $("#progBar").style.width = (100 * n / sections.length) + "%";
    $("#progChip").textContent = PHASES[p][1] + " · " + n + "/" + sections.length;
    $$("#phaseTrack .chip").forEach(function (chip, i) {
      chip.classList.toggle("on", i === p);
      chip.classList.toggle("past", i < p);
    });
  }
  $$("input[data-done]").forEach(function (box) {
    box.checked = !!state.done[box.dataset.done];
    box.addEventListener("change", function () { state.done[box.dataset.done] = box.checked; save(); refreshProgress(); });
  });
  refreshProgress();

  /* ---------- collapse ---------- */
  sections.forEach(function (sec) {
    $(".collapse", sec).addEventListener("click", function () {
      var collapsed = sec.classList.toggle("collapsed");
      this.setAttribute("aria-expanded", String(!collapsed));
      labelBackgrounds(sec);
    });
  });
  $("#expandAll").addEventListener("click", function () {
    sections.forEach(function (s) { s.classList.remove("collapsed"); });
    $$("main details.sub").forEach(function (d) { d.open = true; });
    labelBackgrounds(document);
  });
  $("#collapseAll").addEventListener("click", function () { sections.forEach(function (s) { s.classList.add("collapsed"); }); });

  /* ---------- active section ---------- */
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        $$("a", toc).forEach(function (a) { a.classList.toggle("active", a.getAttribute("href") === "#" + e.target.id); });
      });
    }, { rootMargin: "-25% 0px -65% 0px" });
    sections.forEach(function (s) { io.observe(s); });
  }

  /* ---------- search with highlighting ---------- */
  var search = $("#search"), info = $("#searchInfo");
  function clearMarks() {
    $$("mark.hl").forEach(function (m) {
      var parent = m.parentNode;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    });
  }
  function highlight(sec, q) {
    var walker = document.createTreeWalker(sec, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue || node.nodeValue.toLowerCase().indexOf(q) < 0) return NodeFilter.FILTER_REJECT;
        for (var p = node.parentNode; p && p !== sec; p = p.parentNode) {
          if (p.namespaceURI === NS || p.nodeName === "BUTTON" || p.nodeName === "SCRIPT") return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], node, count = 0;
    while ((node = walker.nextNode())) nodes.push(node);
    nodes.forEach(function (n) {
      var text = n.nodeValue, lower = text.toLowerCase(), frag = document.createDocumentFragment(), i = 0, j;
      while ((j = lower.indexOf(q, i)) >= 0) {
        frag.appendChild(document.createTextNode(text.slice(i, j)));
        var m = document.createElement("mark"); m.className = "hl"; m.textContent = text.slice(j, j + q.length);
        frag.appendChild(m); count++; i = j + q.length;
      }
      frag.appendChild(document.createTextNode(text.slice(i)));
      n.parentNode.replaceChild(frag, n);
    });
    return count;
  }
  var timer = null;
  function runSearch() {
    var q = search.value.trim().toLowerCase();
    clearMarks();
    if (!q) {
      sections.forEach(function (s) { s.classList.remove("hidden"); });
      $$("li", toc).forEach(function (li) { li.classList.remove("hidden"); });
      info.textContent = "";
      return;
    }
    var hits = 0, secs = 0;
    sections.forEach(function (s) {
      var match = s.textContent.toLowerCase().indexOf(q) >= 0;
      s.classList.toggle("hidden", !match);
      var li = toc.querySelector('li[data-target="' + s.id + '"]');
      if (li) li.classList.toggle("hidden", !match);
      if (!match) return;
      secs++;
      s.classList.remove("collapsed");
      $$("details", s).forEach(function (d) { if (d.textContent.toLowerCase().indexOf(q) >= 0) d.open = true; });
      hits += highlight(s, q);
    });
    info.textContent = secs ? (hits + " התאמות ב־" + secs + " נושאים") : "אין תוצאות. נסו מונח באנגלית, למשל dedupe_key";
  }
  search.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(runSearch, 180); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== search && !/INPUT|TEXTAREA/.test(document.activeElement.nodeName)) { e.preventDefault(); search.focus(); }
    else if (e.key === "Escape" && document.activeElement === search) { search.value = ""; runSearch(); search.blur(); }
  });

  /* ---------- chrome ---------- */
  $("#menuBtn").addEventListener("click", function () {
    var open = document.body.classList.toggle("menu-open");
    this.setAttribute("aria-expanded", String(open));
  });
  $("#toTop").addEventListener("click", function () { window.scrollTo({ top: 0 }); });

  /* ---------- copy buttons on code ---------- */
  $$("main pre").forEach(function (pre) {
    var box = document.createElement("div"); box.className = "codebox";
    pre.parentNode.insertBefore(box, pre); box.appendChild(pre);
    var b = document.createElement("button"); b.className = "copy"; b.type = "button"; b.textContent = "העתק";
    b.addEventListener("click", function () {
      var text = pre.innerText;
      var done = function () { b.textContent = "הועתק"; setTimeout(function () { b.textContent = "העתק"; }, 1400); };
      var fallback = function () {
        var r = document.createRange(); r.selectNodeContents(pre);
        var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = "סומן — Ctrl/⌘+C";
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
      else fallback();
    });
    box.appendChild(b);
  });

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

  /* ---------- drills ---------- */
  function drill(selector, btnId) {
    var b = document.getElementById(btnId);
    if (!b) return;
    b.addEventListener("click", function () {
      var items = $$(selector);
      items.forEach(function (d) { d.open = false; d.classList.remove("flash"); });
      var pick = items[Math.floor(Math.random() * items.length)];
      pick.closest("section").classList.remove("collapsed");
      if (pick.classList.contains("recipe")) pick.open = true;
      if (pick.scrollIntoView) pick.scrollIntoView({ block: "center" });
      void pick.offsetWidth; pick.classList.add("flash");
    });
  }
  drill("details.recipe", "drillRecipe");
  drill("details.qa", "drillQa");
  var openAll = $("#qaOpenAll");
  if (openAll) openAll.addEventListener("click", function () {
    var qs = $$("details.qa"), anyClosed = qs.some(function (d) { return !d.open; });
    qs.forEach(function (d) { d.open = anyClosed; });
    openAll.textContent = anyClosed ? "הסתר את כל התשובות" : "חשוף את כל התשובות";
  });

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
  labelBackgrounds(document);
  $$("main details").forEach(function (d) { d.addEventListener("toggle", function () { if (d.open) labelBackgrounds(d); }); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () {
    $$("svg.dg rect.lblbg").forEach(function (r) { r.remove(); });
    $$("svg.dg text.lbl").forEach(function (t) { delete t.dataset.bg; });
    labelBackgrounds(document);
  });

  /* ---------- open the section named in the hash ---------- */
  if (location.hash) {
    var target = document.getElementById(location.hash.slice(1));
    if (target && target.classList.contains("topic")) target.classList.remove("collapsed");
  }
})();
