/* LolSuit study guide — core: theme, topics, progress, navigation, search, copy buttons.
   Shares window.Guide with diagrams.js (loaded first), code-viewer.js and palette.js. */
(function () {
  "use strict";
  var STORE = "lolsuit-study-v2";
  function load() { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch (e) { return {}; } }
  function save() { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { /* storage blocked */ } }
  var state = load();
  state.done = state.done || {};
  var NS = "http://www.w3.org/2000/svg";
  var Guide = window.Guide = window.Guide || {};
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
  // A topic's own number (the exam finder is 0); only topics with a "learned" box count toward progress.
  function numOf(sec) { var n = $(".topic-head .n", sec); return n ? n.textContent.trim() : ""; }
  var studied = sections.filter(function (s) { return !!$("input[data-done]", s); });
  sections.forEach(function (sec, i) {
    var li = document.createElement("li");
    li.dataset.target = sec.id;
    var a = document.createElement("a");
    a.href = "#" + sec.id;
    a.innerHTML = '<span class="num"></span><span></span><span class="chk" aria-hidden="true">✔</span>';
    a.children[0].textContent = numOf(sec).padStart(2, "0");
    a.children[1].textContent = sec.dataset.title;
    a.addEventListener("click", function (e) {
      document.body.classList.remove("menu-open");
      sec.classList.remove("collapsed");
      if (state.mode !== "all") { e.preventDefault(); go(sec.id, true); }
    });
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
    studied.forEach(function (sec) {
      var done = !!state.done[sec.id];
      if (done) n++;
      var li = toc.querySelector('li[data-target="' + sec.id + '"]');
      if (li) li.classList.toggle("done", done);
    });
    var p = phaseIndex(n, studied.length);
    $("#progBar").style.width = (100 * n / studied.length) + "%";
    $("#progChip").textContent = PHASES[p][1] + " · " + n + "/" + studied.length;
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

  /* ---------- one topic at a time, with previous / next ---------- */
  var ids = sections.map(function (s) { return s.id; });
  var current = ids[0];
  function titleOf(i) { return numOf(sections[i]) + ". " + sections[i].dataset.title; }
  sections.forEach(function (sec, i) {
    var pos = document.createElement("span");
    pos.className = "topic-pos";
    pos.textContent = studied.indexOf(sec) >= 0 ? "נושא " + numOf(sec) + " מתוך " + studied.length : "כלי עבודה למבחן";
    $(".topic-head", sec).insertBefore(pos, $(".done-toggle", sec) || $(".collapse", sec));
    var pager = document.createElement("nav");
    pager.className = "pager";
    pager.setAttribute("aria-label", "מעבר בין נושאים");
    var prev = i > 0
      ? '<a class="prev" href="#' + ids[i - 1] + '" data-go="' + ids[i - 1] + '"><span class="dir">→ הקודם</span><span class="ttl"></span></a>'
      : '<span class="empty"></span>';
    var next = i < sections.length - 1
      ? '<a class="next cta" href="#' + ids[i + 1] + '" data-go="' + ids[i + 1] + '"><span class="dir">הבא ←</span><span class="ttl"></span></a>'
      : '<span class="empty"></span>';
    pager.innerHTML = prev + next +
      '<button class="btn done-next" type="button">' + (!$("input[data-done]", sec) ? "לנושא הבא" : i < sections.length - 1 ? "סמן כנלמד ועבור לנושא הבא" : "סמן כנלמד") + '</button>';
    if (i > 0) $(".prev .ttl", pager).textContent = titleOf(i - 1);
    if (i < sections.length - 1) $(".next .ttl", pager).textContent = titleOf(i + 1);
    $(".done-next", pager).addEventListener("click", function () {
      var box = $("input[data-done]", sec);
      if (box) { box.checked = true; state.done[sec.id] = true; save(); refreshProgress(); }
      if (i < sections.length - 1) go(ids[i + 1], true);
    });
    sec.appendChild(pager);
  });
  document.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("[data-go]");
    if (!link || state.mode === "all") return;
    e.preventDefault();
    go(link.getAttribute("data-go"), true);
  });
  function markActive(id) {
    $$("a", toc).forEach(function (a) { a.classList.toggle("active", a.getAttribute("href") === "#" + id); });
  }
  function go(id, push) {
    if (ids.indexOf(id) < 0) id = ids[0];
    current = id;
    state.current = id; save();
    document.body.classList.toggle("first", id === ids[0]);
    sections.forEach(function (s) { s.classList.toggle("off", s.id !== id); });
    markActive(id);
    if (push && location.hash !== "#" + id) {
      try { history.pushState(null, "", "#" + id); } catch (e) { /* file:// in some browsers */ }
    }
    if (state.mode !== "all") {
      window.scrollTo({ top: 0 });
      var sec = document.getElementById(id);
      if (sec) labelBackgrounds(sec);
    }
  }
  function applyMode() {
    var focus = state.mode !== "all";
    document.body.classList.toggle("focus", focus);
    $("#modeBtn").textContent = focus ? "הצג את כל הנושאים ברצף" : "הצג נושא אחד בכל פעם";
    if (focus) go(current, false); else labelBackgrounds(document);
  }
  $("#modeBtn").addEventListener("click", function () {
    state.mode = state.mode === "all" ? "focus" : "all"; save();
    applyMode();
    if (state.mode === "all") { var s = document.getElementById(current); if (s && s.scrollIntoView) s.scrollIntoView(); }
  });
  window.addEventListener("hashchange", function () {
    var id = location.hash.slice(1);
    if (ids.indexOf(id) >= 0 && state.mode !== "all") go(id, false);
  });
  document.addEventListener("keydown", function (e) {
    if (state.mode === "all" || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.nodeName) || document.body.classList.contains("searching") || document.body.classList.contains("overlay")) return;
    var i = ids.indexOf(current);
    // Right-to-left page: the left arrow moves forward.
    if (e.key === "ArrowLeft" && i < ids.length - 1) { e.preventDefault(); go(ids[i + 1], true); }
    if (e.key === "ArrowRight" && i > 0) { e.preventDefault(); go(ids[i - 1], true); }
  });

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

  /* ---------- active section ---------- */
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      if (state.mode !== "all") return;
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        current = e.target.id;
        markActive(e.target.id);
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
    document.body.classList.toggle("searching", !!q);
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
    if (e.key === "Escape" && document.activeElement === search) { search.value = ""; runSearch(); search.blur(); }
  });

  /* ---------- chrome ---------- */
  $("#menuBtn").addEventListener("click", function () {
    var open = document.body.classList.toggle("menu-open");
    this.setAttribute("aria-expanded", String(open));
  });
  $("#toTop").addEventListener("click", function () { window.scrollTo({ top: 0 }); });

  /* ---------- copy buttons on code ---------- */
  /* diagrams.js owns label backgrounds; topics call it as they become visible */
  function labelBackgrounds(scope) { if (Guide.labelBackgrounds) Guide.labelBackgrounds(scope); }

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

  /* ---------- reveal: bring any element into view, whatever the mode ---------- */
  function reveal(target) {
    if (!target) return;
    if (search.value) { search.value = ""; runSearch(); }
    var owner = target.closest("section.topic");
    if (owner) {
      owner.classList.remove("collapsed");
      if (state.mode !== "all" && owner.id !== current) go(owner.id, true);
    }
    for (var d = target.closest("details"); d; d = d.parentNode.closest("details")) d.open = true;
    if (target.nodeName === "DETAILS") target.open = true;
    document.body.classList.remove("menu-open");
    setTimeout(function () {
      if (target.scrollIntoView) target.scrollIntoView({ block: "center" });
      target.classList.remove("flash"); void target.offsetWidth; target.classList.add("flash");
    }, 30);
  }
  Guide.reveal = reveal;

  /* ---------- drills ---------- */
  function drill(selector, btnId) {
    var b = document.getElementById(btnId);
    if (!b) return;
    b.addEventListener("click", function () {
      var items = $$(selector);
      items.forEach(function (d) { d.open = false; d.classList.remove("flash"); });
      reveal(items[Math.floor(Math.random() * items.length)]);
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

  /* ---------- start on the topic named in the hash, else where the reader left off ---------- */
  var fromHash = location.hash.slice(1);
  current = ids.indexOf(fromHash) >= 0 ? fromHash : (ids.indexOf(state.current) >= 0 ? state.current : ids[0]);
  applyMode();
})();
