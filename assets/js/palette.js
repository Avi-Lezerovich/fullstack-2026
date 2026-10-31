/* LolSuit study guide — quick-find palette (Ctrl+K or /) over the finder, recipes, topics,
   exam questions, code symbols and files; plus the finder's own filter. Needs code-viewer.js. */
(function () {
  "use strict";
  var Guide = window.Guide = window.Guide || {};
  var IDX = window.GUIDE_CODE_INDEX || { files: {}, symbols: [] };
  var FILES = Object.keys(IDX.files);
  var isTest = Guide.isTest;
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function norm(s) { return String(s || "").toLowerCase().replace(/[־_\-./:()"'`,]/g, " ").replace(/\s+/g, " ").trim(); }

  /* ---------- quick-find palette ---------- */
  var palette = document.createElement("dialog");
  palette.className = "palette"; palette.id = "palette";
  palette.setAttribute("aria-label", "חיפוש מהיר");
  palette.innerHTML =
    '<div class="pal-in"><span class="pal-ic" aria-hidden="true">⌕</span>' +
    '<input type="search" class="pal-q" placeholder="מה ביקשו לשנות? סיסמה, צבע, כפתור, endpoint, PANEL_SIZE…" aria-label="חיפוש מהיר" autocomplete="off" spellcheck="false">' +
    '<button class="btn pal-x" type="button">Esc</button></div>' +
    '<div class="pal-list" role="listbox"></div>' +
    '<div class="pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd> בחירה</span><span><kbd>Enter</kbd> פתיחה</span><span><kbd>Esc</kbd> סגירה</span><span>מחפש במדריך, במתכונים, בשמות בקוד ובקבצים</span></div>';
  document.body.appendChild(palette);
  var palQ = $(".pal-q", palette), palList = $(".pal-list", palette);
  var ITEMS = null, shown = [], sel = 0;
  var TYPES = {
    finder: ["איפה זה?", 0], recipe: ["מתכון", 1], guide: ["במדריך", 2], qa: ["שאלת מבחן", 3],
    code: ["בקוד", 2], file: ["קובץ", 4], grep: ["חיפוש בקוד", 5]
  };
  function txt(el) { return el ? el.textContent.replace(/\s+/g, " ").trim() : ""; }
  function topicOf(el) { var s = el.closest("section.topic"); return s ? s.dataset.title : ""; }
  function buildItems() {
    var items = [];
    $$(".fx").forEach(function (el) {
      items.push({ type: "finder", title: txt($(".fx-q", el)), sub: txt($(".fx-where", el)), keys: (el.dataset.keys || "") + " " + txt(el), el: el });
    });
    $$("details.recipe").forEach(function (el) {
      items.push({ type: "recipe", title: txt($("summary", el)).replace(/^(קל|בינוני|מתקדם)\s*/, ""), sub: "Cookbook", keys: txt(el).slice(0, 1500), el: el });
    });
    $$("details.qa").forEach(function (el) {
      items.push({ type: "qa", title: txt($("summary", el)), sub: topicOf(el), keys: "", el: el });
    });
    $$("section.topic").forEach(function (sec) {
      items.push({ type: "guide", title: txt($(".topic-head h2", sec)), sub: "נושא", keys: "", el: sec });
      $$("details.sub > summary, .topic-body h3, .topic-body h4, .card > h4, dt, .gl-term", sec).forEach(function (h) {
        var host = h.nodeName === "SUMMARY" ? h.parentNode : h;
        if (host.closest(".fx")) return;
        items.push({ type: "guide", title: txt(h), sub: sec.dataset.title, keys: h.nodeName === "DT" && h.nextElementSibling ? txt(h.nextElementSibling) : "", el: host });
      });
    });
    IDX.symbols.forEach(function (s) {
      items.push({ type: "code", title: s[0], sub: s[2] + ":" + s[3] + " · " + s[1], keys: s[2], path: s[2], line: s[3], test: isTest(s[2]) });
    });
    FILES.forEach(function (f) { items.push({ type: "file", title: f.split("/").pop(), sub: f, keys: f, path: f, test: isTest(f) }); });
    items.forEach(function (it, i) {
      it.nt = norm(it.title); it.hay = norm(it.title + " " + it.sub + " " + it.keys);
      if (it.el && !it.el.id) it.el.id = "pal-" + i; // so "recent" can find it again after a reload
    });
    return items;
  }

  /* recently opened, newest first, kept in this browser */
  var RECENT_KEY = "lolsuit-recent-v1", RECENT_MAX = 6;
  function loadRecent() { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]") || []; } catch (e) { return []; } }
  function remember(it) {
    if (it.action) return;
    var rec = { type: it.type, title: it.title, sub: (it.sub || "").replace(/^אחרון · /, ""), path: it.path, line: it.line, q: it.q, elId: it.el ? it.el.id : null };
    var list = loadRecent().filter(function (r) { return !(r.type === rec.type && r.title === rec.title && r.sub === rec.sub); });
    list.unshift(rec);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX))); } catch (e) { /* storage blocked */ }
  }
  function recentItems() {
    return loadRecent().map(function (r) {
      var it = { type: r.type, title: r.title, sub: "אחרון · " + (r.sub || ""), path: r.path, line: r.line, q: r.q };
      if (r.elId) { it.el = document.getElementById(r.elId); if (!it.el) return null; }
      return it;
    }).filter(Boolean);
  }
  var LIMIT = { finder: 8, recipe: 5, guide: 6, qa: 3, code: 8, file: 5 };
  function score(it, q, toks) {
    for (var i = 0; i < toks.length; i++) if (it.hay.indexOf(toks[i]) < 0) return null; // scores can go below zero, so "no match" is null
    var s = TYPES[it.type][1] * 10;
    if (it.nt === q) s -= 40;
    else if (it.nt.indexOf(q) === 0) s -= 20;
    else if (it.nt.indexOf(q) >= 0) s -= 12;
    else if (toks.every(function (t) { return it.nt.indexOf(t) >= 0; })) s -= 6;
    if (it.test) s += 15;
    return s;
  }
  function render() {
    var raw = palQ.value.trim(), q = norm(raw), toks = q.split(" ").filter(Boolean);
    if (!ITEMS) ITEMS = buildItems();
    if (!q) {
      shown = recentItems().concat([
        { type: "guide", title: "מצב מבחן — איפה זה?", sub: "אינדקס: ביקשו לשנות X, איפה זה", el: document.getElementById("t0") },
        { type: "guide", title: "Small change cookbook", sub: "מתכונים צעד־אחר־צעד", el: document.getElementById("t13") },
        { type: "guide", title: "תרגול תחת שעון", sub: "משימה אקראית, טיימר ופתרון מוסתר", el: document.getElementById("t20") },
        { type: "guide", title: "תקלות נפוצות", sub: "משהו לא עובד? פתרונות מהירים", el: document.getElementById("t19") },
        { type: "file", title: "כל הקבצים", sub: "עץ הקבצים של הפרויקט", action: "files" },
        { type: "grep", title: "חיפוש בכל הקוד", sub: "כמו grep -rn, בתוך הדפדפן", action: "grep" }
      ].filter(function (it) { return it.el !== null; }));
    } else {
      var scored = ITEMS.map(function (it) { return [score(it, q, toks), it]; }).filter(function (x) { return x[0] !== null; });
      scored.sort(function (a, b) { return a[0] - b[0]; });
      var per = {};
      shown = [];
      scored.forEach(function (x) {
        var t = x[1].type; per[t] = (per[t] || 0) + 1;
        if (per[t] <= LIMIT[t]) shown.push(x[1]);
      });
      shown = shown.slice(0, 30);
      shown.push({ type: "grep", title: "חפש \"" + raw + "\" בכל הקוד", sub: "כל המופעים, קובץ:שורה", q: raw });
    }
    sel = 0;
    palList.innerHTML = shown.map(function (it, i) {
      return '<div class="pal-row" role="option" data-i="' + i + '"' + (i === 0 ? ' aria-selected="true"' : "") + ">" +
        '<span class="pal-type t-' + it.type + '">' + TYPES[it.type][0] + "</span>" +
        '<span class="pal-main"><span class="pal-title">' + esc(it.title) + '</span><span class="pal-sub">' + esc(it.sub || "") + "</span></span></div>";
    }).join("");
  }
  function move(d) {
    var rows = $$(".pal-row", palList); if (!rows.length) return;
    rows[sel].removeAttribute("aria-selected");
    sel = (sel + d + rows.length) % rows.length;
    rows[sel].setAttribute("aria-selected", "true");
    rows[sel].scrollIntoView({ block: "nearest" });
  }
  function choose(i) {
    var it = shown[i]; if (!it) return;
    closePalette();
    remember(it);
    if (it.action === "files") Guide.openPane("files");
    else if (it.action === "grep") Guide.openPane("grep");
    else if (it.type === "grep") Guide.openGrep(it.q);
    else if (it.path) Guide.openFile(it.path, it.line || 0, it.line || 0);
    else if (it.el && Guide.reveal) Guide.reveal(it.el);
  }
  function openPalette(q) {
    if (palette.open) return;
    if (palette.showModal) palette.showModal(); else palette.setAttribute("open", "");
    document.body.classList.add("overlay");
    palQ.value = q || ""; render();
    setTimeout(function () { palQ.focus(); palQ.select(); }, 0);
  }
  function closePalette() {
    if (palette.close) palette.close(); else palette.removeAttribute("open");
  }
  palette.addEventListener("close", function () { document.body.classList.remove("overlay"); });
  palette.addEventListener("click", function (e) {
    if (e.target === palette) { closePalette(); return; }
    var r = e.target.closest(".pal-row"); if (r) choose(Number(r.dataset.i));
  });
  $(".pal-x", palette).addEventListener("click", closePalette);
  var palTimer;
  palQ.addEventListener("input", function () { clearTimeout(palTimer); palTimer = setTimeout(render, 90); });
  palQ.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { e.preventDefault(); clearTimeout(palTimer); render(); choose(sel); }
  });
  palette.addEventListener("keydown", function (e) { e.stopPropagation(); });

  document.addEventListener("keydown", function (e) {
    var typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.nodeName);
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); openPalette(); }
    else if (e.key === "/" && !typing) { e.preventDefault(); openPalette(); }
  });

  /* ---------- buttons in the page ---------- */
  $$("[data-open-palette]").forEach(function (b) { b.addEventListener("click", function () { openPalette(); }); });
  var side = $("#search");
  if (side) side.setAttribute("placeholder", "סינון הנושאים (לחיפוש מהיר: Ctrl+K)");

  /* the finder's own filter */
  var fxIn = $("#fxFilter");
  if (fxIn) fxIn.addEventListener("input", function () {
    var toks = norm(fxIn.value).split(" ").filter(Boolean), n = 0;
    $$(".fx").forEach(function (el) {
      var hay = norm(el.textContent + " " + (el.dataset.keys || ""));
      var on = toks.every(function (t) { return hay.indexOf(t) >= 0; });
      el.hidden = !on; if (on) n++;
    });
    $$(".fx-group").forEach(function (g) { g.hidden = !$$(".fx", g).some(function (el) { return !el.hidden; }); });
    $("#fxCount").textContent = toks.length ? n + " רשומות" : "";
  });

  Guide.openPalette = openPalette;
})();
