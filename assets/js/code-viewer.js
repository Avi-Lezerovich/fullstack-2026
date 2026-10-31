/* LolSuit study guide — code viewer: the code pane, in-browser grep, and links from every
   file/symbol mention in the guide into the code. Needs data/code-index.js; data/code.js
   (file contents) and highlight.js load in the background. */
(function () {
  "use strict";
  var Guide = window.Guide = window.Guide || {};
  var IDX = window.GUIDE_CODE_INDEX || { files: {}, symbols: [] };
  var FILES = Object.keys(IDX.files);
  var CODE = null;
  var HLJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js";
  var LH = 20, PAD = 10; // code line height and top padding, in px (kept in sync with .cp-*)

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function norm(s) { return String(s || "").toLowerCase().replace(/[־_\-./:()"'`,]/g, " ").replace(/\s+/g, " ").trim(); }
  function isTest(p) { return /\/tests\/|\.test\.tsx?$|\/test\/|^server\/evals\//.test(p); }

  /* ---------- background loading ---------- */
  var waiters = [], loading = false;
  function addScript(src, cb) {
    var s = document.createElement("script");
    s.src = src; s.async = true;
    s.onload = function () { cb(true); };
    s.onerror = function () { cb(false); };
    document.head.appendChild(s);
  }
  function withCode(cb) {
    if (CODE) { cb(); return; }
    waiters.push(cb);
    if (loading) return;
    loading = true;
    var left = 2;
    function done() { if (--left) return; CODE = window.GUIDE_CODE || {}; loading = false; waiters.splice(0).forEach(function (fn) { fn(); }); }
    addScript("assets/data/code.js?v=" + IDX.commit, function (ok) { if (!ok) toast("לא הצלחתי לטעון את הקוד, רעננו את הדף"); done(); });
    if (window.hljs) done(); else addScript(HLJS_URL, done);
  }
  setTimeout(function () { withCode(function () {}); }, 1500);

  /* ---------- paths and symbols ---------- */
  function resolvePath(p) {
    if (IDX.files[p]) return p;
    var hits = FILES.filter(function (f) { return f.slice(-p.length - 1) === "/" + p; });
    if (hits.length > 1) hits = hits.filter(function (f) { return !isTest(f); });
    return hits.length === 1 ? hits[0] : null;
  }
  var DEFS = {};
  IDX.symbols.forEach(function (s) { (DEFS[s[0]] = DEFS[s[0]] || []).push(s); });
  function defOf(name) {
    var all = (DEFS[name] || []).filter(function (s) { return !isTest(s[2]); });
    if (!all.length) return null;
    var paths = {};
    all.forEach(function (s) { paths[s[2]] = 1; });
    return Object.keys(paths).length === 1 ? all[0] : null;
  }

  /* ---------- toast ---------- */
  var toastEl = document.createElement("div");
  toastEl.className = "toast"; toastEl.setAttribute("role", "status");
  document.body.appendChild(toastEl);
  var toastTimer;
  function toast(msg) {
    toastEl.textContent = msg; toastEl.classList.add("on");
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toastEl.classList.remove("on"); }, 1800);
  }
  function copy(text, label) {
    function ok() { toast("הועתק: " + (label || text)); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, function () { window.prompt("העתיקו:", text); });
    else window.prompt("העתיקו:", text);
  }

  /* ---------- the code pane ---------- */
  var pane = document.createElement("aside");
  pane.className = "codepane"; pane.id = "codePane"; pane.hidden = true;
  pane.setAttribute("aria-label", "צפייה בקוד");
  pane.innerHTML =
    '<div class="cp-head">' +
      '<div class="seg cp-tabs" role="tablist">' +
        '<button type="button" data-tab="file" aria-pressed="true">קובץ</button>' +
        '<button type="button" data-tab="files" aria-pressed="false">כל הקבצים</button>' +
        '<button type="button" data-tab="grep" aria-pressed="false">חיפוש בכל הקוד</button>' +
      '</div><span class="grow"></span>' +
      '<button class="btn cp-wide" type="button" title="הרחב/צמצם">⇔</button>' +
      '<button class="btn cp-close" type="button" aria-label="סגור">✕ סגור</button>' +
    '</div>' +
    '<div class="cp-view" data-view="file">' +
      '<div class="cp-bar">' +
        '<code class="cp-path">בחרו קובץ</code>' +
        '<button class="btn cp-copy" type="button" title="מדביקים ב־Ctrl+P ב־VS Code וקופצים ישר לשורה">העתק נתיב:שורה</button>' +
        '<button class="btn primary cp-vscode" type="button" title="פותח את הקובץ, בשורה הזו, ב־VS Code במחשב שלך">פתח ב־VS Code</button>' +
        '<a class="btn cp-gh" target="_blank" rel="noopener">GitHub ↗</a>' +
        '<span class="cp-find"><input class="search" type="search" placeholder="חיפוש בקובץ (Enter = הבא)" aria-label="חיפוש בקובץ"><span class="cp-find-info"></span></span>' +
      '</div>' +
      '<div class="cp-usage" aria-live="polite"><span class="cp-usage-hint">טיפ: לחיצה על שם בקוד (פונקציה, קבוע, משתנה) מראה איפה עוד משתמשים בו</span></div>' +
      '<div class="cp-code" tabindex="0" title="לחיצה על שם: איפה עוד משתמשים בו"><div class="cp-empty">טוען קוד…</div></div>' +
    '</div>' +
    '<div class="cp-view" data-view="files" hidden>' +
      '<input class="search cp-filter" type="search" placeholder="סינון קבצים, למשל NewCase או api/cases" aria-label="סינון קבצים">' +
      '<div class="cp-list"></div>' +
    '</div>' +
    '<div class="cp-view" data-view="grep" hidden>' +
      '<form class="cp-grepform">' +
        '<input class="search cp-q" type="search" placeholder="טקסט לחיפוש בכל הקבצים, למשל איסוף עדויות או MIN_PASSWORD" aria-label="חיפוש בכל הקוד">' +
        '<div class="cp-opts">' +
          '<input class="search cp-where" type="text" placeholder="רק בנתיב: client/ או .py" aria-label="סינון נתיב">' +
          '<label><input type="checkbox" class="cp-notests"> בלי טסטים</label>' +
          '<label><input type="checkbox" class="cp-case"> רגיש לאותיות</label>' +
          '<label><input type="checkbox" class="cp-regex"> regex</label>' +
          '<button class="btn primary" type="submit">חפש</button>' +
        '</div>' +
      '</form>' +
      '<div class="cp-ginfo"></div><div class="cp-results"></div>' +
    '</div>';
  document.body.appendChild(pane);
  var codeBox = $(".cp-code", pane), pathEl = $(".cp-path", pane), ghEl = $(".cp-gh", pane);
  var findIn = $(".cp-find input", pane), findInfo = $(".cp-find-info", pane);
  var cur = { path: null, line: 0, end: 0 };

  function showTab(tab) {
    $$(".cp-tabs button", pane).forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.tab === tab)); });
    $$(".cp-view", pane).forEach(function (v) { v.hidden = v.dataset.view !== tab; });
    if (tab === "files") { renderList(); setTimeout(function () { $(".cp-filter", pane).focus(); }, 0); }
    if (tab === "grep") setTimeout(function () { $(".cp-q", pane).focus(); }, 0);
  }
  function openPane(tab) {
    pane.hidden = false;
    document.body.classList.add("pane-open");
    showTab(tab || "file");
  }
  function closePane() {
    pane.hidden = true;
    document.body.classList.remove("pane-open");
  }
  $(".cp-tabs", pane).addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (b) showTab(b.dataset.tab);
  });
  $(".cp-close", pane).addEventListener("click", closePane);
  $(".cp-wide", pane).addEventListener("click", function () { pane.classList.toggle("wide"); });
  pane.addEventListener("keydown", function (e) {
    if (/^Arrow/.test(e.key)) e.stopPropagation(); // arrows here scroll code, they do not change topic
    if (e.key === "Escape" && !document.querySelector("dialog.palette[open]")) closePane();
  });

  function langOf(p) {
    var name = p.split("/").pop();
    if (/\.py$/.test(p)) return "python";
    if (/\.tsx?$/.test(p)) return "typescript";
    if (/\.sql$/.test(p)) return "sql";
    if (/\.ya?ml$/.test(p)) return "yaml";
    if (/\.(sh)$/.test(p) || name === "Dockerfile") return "bash";
    if (/\.md$/.test(p)) return "markdown";
    if (/\.json$/.test(p)) return "json";
    if (/\.html$/.test(p)) return "xml";
    if (name === "Makefile") return "makefile";
    if (/\.(ini|example|template)$/.test(p) || name === ".env.example") return "ini";
    return null;
  }
  function band(cls, from, to) {
    var b = document.createElement("div");
    b.className = cls;
    b.style.top = (PAD + (from - 1) * LH) + "px";
    b.style.height = ((to - from + 1) * LH) + "px";
    return b;
  }
  function scrollToLine(n) {
    codeBox.scrollTop = Math.max(0, PAD + (n - 1) * LH - codeBox.clientHeight / 3);
  }
  function setLine(line, end) {
    cur.line = line || 0; cur.end = end && end > line ? end : cur.line;
    $$(".cp-band", codeBox).forEach(function (b) { b.remove(); });
    if (cur.line) { $(".cp-inner", codeBox).appendChild(band("cp-band", cur.line, cur.end)); scrollToLine(cur.line); }
    ghEl.href = IDX.repo + "/blob/" + IDX.commit + "/" + cur.path + (cur.line ? "#L" + cur.line + (cur.end > cur.line ? "-L" + cur.end : "") : "");
  }
  // `term` (optional) is highlighted on every line it appears on, e.g. the grep query.
  function openFile(path, line, end, term) {
    openPane("file");
    cur.path = path;
    pathEl.textContent = path + (line ? ":" + line : "");
    findIn.value = ""; findInfo.textContent = "";
    resetUsage();
    codeBox.innerHTML = '<div class="cp-empty">טוען קוד…</div>';
    withCode(function () {
      if (cur.path !== path) return;
      var text = CODE[path];
      if (text == null) { codeBox.innerHTML = '<div class="cp-empty">הקובץ לא נמצא בצילום הקוד.</div>'; return; }
      var n = text.split("\n").length, html = null, lang = langOf(path);
      if (window.hljs && lang && text.length < 300000) {
        try { html = window.hljs.highlight(text, { language: lang, ignoreIllegals: true }).value; } catch (e) { html = null; }
      }
      var gutter = [];
      for (var i = 1; i <= n; i++) gutter.push('<span data-ln="' + i + '">' + i + "</span>");
      codeBox.innerHTML = '<div class="cp-inner"><div class="cp-gutter">' + gutter.join("") +
        '</div><pre class="cp-src"><code class="hljs">' + (html || esc(text)) + "</code></pre></div>";
      setLine(line, end);
      if (!line) codeBox.scrollTop = 0;
      if (term) { findIn.value = term; runFind(line); }
    });
  }
  codeBox.addEventListener("click", function (e) {
    var ln = e.target.closest && e.target.closest("[data-ln]");
    if (ln) {
      var n = Number(ln.dataset.ln);
      setLine(n, n);
      pathEl.textContent = cur.path + ":" + n;
      copy(cur.path + ":" + n);
      return;
    }
    if (e.target.closest && e.target.closest(".cp-src") && !String(window.getSelection() || "")) showUsage(wordAt(e));
  });

  /* find usages: click a name in the code */
  var usageBar = $(".cp-usage", pane), usageHint = usageBar.innerHTML;
  function resetUsage() { usageBar.innerHTML = usageHint; usageBar.classList.remove("on"); }
  function wordAt(e) {
    var node = null, off = 0;
    if (document.caretRangeFromPoint) {
      var r = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (r) { node = r.startContainer; off = r.startOffset; }
    } else if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(e.clientX, e.clientY);
      if (p) { node = p.offsetNode; off = p.offset; }
    }
    if (!node || node.nodeType !== 3) return "";
    var t = node.nodeValue, a = off, b = off;
    while (a > 0 && /\w/.test(t[a - 1])) a--;
    while (b < t.length && /\w/.test(t[b])) b++;
    return t.slice(a, b);
  }
  function showUsage(word) {
    if (!word || word.length < 3 || /^\d/.test(word) || !CODE) { resetUsage(); return; }
    var rx = new RegExp("\\b" + word + "\\b"), uses = 0, files = 0;
    ORDERED.forEach(function (f) {
      var hits = (CODE[f] || "").split("\n").filter(function (l) { return rx.test(l); }).length;
      if (hits) { uses += hits; files++; }
    });
    var d = defOf(word);
    usageBar.innerHTML = '<code class="cp-uword">' + esc(word) + "</code>" +
      '<span class="cp-ucount">' + uses + " שורות ב־" + files + " קבצים</span>" +
      (d ? '<button class="btn" type="button" data-u="def">הגדרה: ' + esc(d[2].split("/").pop() + ":" + d[3]) + "</button>" : "") +
      '<button class="btn primary" type="button" data-u="all">הצג את כל השימושים</button>' +
      '<button class="btn" type="button" data-u="x" aria-label="סגור">✕</button>';
    usageBar.classList.add("on");
    usageBar.onclick = function (ev) {
      var b = ev.target.closest("[data-u]"); if (!b) return;
      if (b.dataset.u === "def") openFile(d[2], d[3], d[3], word);
      else if (b.dataset.u === "all") openGrep("\\b" + word + "\\b", { regex: true, caseSensitive: true });
      else resetUsage();
    };
  }
  $(".cp-copy", pane).addEventListener("click", function () {
    if (cur.path) copy(cur.path + (cur.line ? ":" + cur.line : ""));
  });

  /* open in the local VS Code: vscode://file/<absolute path>:<line>:<column> */
  var LOCAL_ROOT = "C:/Users/lzr/Documents/GitHub/fullstack-2026"; // the exam laptop's checkout
  function openInVSCode(path, line) {
    window.location.href = "vscode://file/" + encodeURI(LOCAL_ROOT + "/" + path) + (line ? ":" + line + ":1" : "");
  }
  $(".cp-vscode", pane).addEventListener("click", function () {
    if (cur.path) openInVSCode(cur.path, cur.line);
  });

  /* in-file find */
  var finds = [], findAt = -1;
  // preferLine: start on that match (opening a grep result) instead of the first one
  function runFind(preferLine) {
    $$(".cp-hit", codeBox).forEach(function (b) { b.remove(); });
    finds = []; findAt = -1;
    var q = findIn.value.toLowerCase(), inner = $(".cp-inner", codeBox);
    if (!q || !inner || !CODE[cur.path]) { findInfo.textContent = ""; return; }
    CODE[cur.path].split("\n").forEach(function (l, i) {
      if (l.toLowerCase().indexOf(q) >= 0) { finds.push(i + 1); inner.appendChild(band("cp-hit", i + 1, i + 1)); }
    });
    var at = typeof preferLine === "number" ? finds.indexOf(preferLine) : -1;
    findAt = at > 0 ? at - 1 : -1;
    stepFind(1);
  }
  function stepFind(dir) {
    if (!finds.length) { findInfo.textContent = findIn.value ? "0" : ""; return; }
    findAt = (findAt + dir + finds.length) % finds.length;
    $$(".cp-hit", codeBox).forEach(function (b, i) { b.classList.toggle("cur", i === findAt); });
    scrollToLine(finds[findAt]);
    findInfo.textContent = (findAt + 1) + "/" + finds.length;
  }
  var findTimer;
  findIn.addEventListener("input", function () { clearTimeout(findTimer); findTimer = setTimeout(runFind, 150); });
  findIn.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); stepFind(e.shiftKey ? -1 : 1); } });

  /* file list */
  var listBox = $(".cp-list", pane), filterIn = $(".cp-filter", pane);
  function renderList() {
    var toks = norm(filterIn.value).split(" ").filter(Boolean);
    var groups = {}, order = [];
    FILES.forEach(function (f) {
      var hay = f.toLowerCase().replace(/[_\-./]/g, " ") + " " + f.toLowerCase();
      if (!toks.every(function (t) { return hay.indexOf(t) >= 0; })) return;
      var dir = f.indexOf("/") >= 0 ? f.slice(0, f.lastIndexOf("/") + 1) : "/";
      if (!groups[dir]) { groups[dir] = []; order.push(dir); }
      groups[dir].push(f);
    });
    listBox.innerHTML = order.length ? order.map(function (d) {
      return '<div class="cp-dir">' + esc(d) + "</div>" + groups[d].map(function (f) {
        return '<button type="button" class="cp-file" data-open="' + esc(f) + '"><span>' + esc(f.slice(d.length - (d === "/" ? 1 : 0))) +
          '</span><small>' + IDX.files[f] + " שורות</small></button>";
      }).join("");
    }).join("") : '<div class="cp-empty">אין קובץ כזה.</div>';
  }
  filterIn.addEventListener("input", renderList);
  filterIn.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { var first = $(".cp-file", listBox); if (first) openFile(first.dataset.open); }
  });
  listBox.addEventListener("click", function (e) {
    var b = e.target.closest(".cp-file"); if (b) openFile(b.dataset.open);
  });

  /* grep across every file */
  var gq = $(".cp-q", pane), gres = $(".cp-results", pane), ginfo = $(".cp-ginfo", pane);
  var RANK = [/^client\/src\//, /^server\/app\//, /^server\/worker\//, /^database\//, /^(docker-compose|Makefile|\.env)/, /^server\/[^/]+$/, /^client\//, /^prod\//, /\/tests\/|\.test\./, /./];
  function rank(f) { for (var i = 0; i < RANK.length; i++) if (RANK[i].test(f)) return i; return RANK.length; }
  var ORDERED = FILES.slice().sort(function (a, b) { return rank(a) - rank(b) || (a < b ? -1 : 1); });
  function runGrep() {
    var q = gq.value;
    if (!q.trim()) { gres.innerHTML = ""; ginfo.textContent = ""; return; }
    ginfo.textContent = "מחפש…";
    withCode(function () {
      var flags = $(".cp-case", pane).checked ? "" : "i", rx;
      try { rx = new RegExp($(".cp-regex", pane).checked ? q : q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), flags); }
      catch (e) { ginfo.textContent = "regex לא תקין: " + e.message; gres.innerHTML = ""; return; }
      var where = $(".cp-where", pane).value.trim().toLowerCase(), noTests = $(".cp-notests", pane).checked;
      var total = 0, nfiles = 0, rowsShown = 0, html = [], CAP = 400;
      ORDERED.forEach(function (f) {
        if (noTests && isTest(f)) return;
        if (where && f.toLowerCase().indexOf(where) < 0) return;
        var lines = (CODE[f] || "").split("\n"), hits = [];
        for (var i = 0; i < lines.length; i++) if (rx.test(lines[i])) hits.push(i);
        if (!hits.length) return;
        nfiles++; total += hits.length;
        if (rowsShown >= CAP) return;
        var rows = hits.slice(0, CAP - rowsShown).map(function (i) {
          var l = lines[i], m = l.match(rx), at = m ? m.index : 0, from = Math.max(0, at - 70);
          var hl = esc((from ? "…" : "") + l.slice(from, from + 200).trim());
          if (m && m[0]) { var safe = esc(m[0]); hl = hl.split(safe).join("<mark>" + safe + "</mark>"); }
          return '<button type="button" class="cp-gl" data-open="' + esc(f) + '" data-ln="' + (i + 1) + '"><span class="n">' + (i + 1) + "</span><code>" + hl + "</code></button>";
        });
        rowsShown += rows.length;
        html.push('<div class="cp-gfile"><button type="button" class="cp-gpath" data-open="' + esc(f) + '">' + esc(f) +
          '</button><span class="cnt">' + hits.length + "</span>" + (isTest(f) ? '<span class="t">טסט</span>' : "") + "</div>" + rows.join(""));
      });
      gres.innerHTML = html.join("") || '<div class="cp-empty">אין התאמות.</div>';
      ginfo.textContent = total ? total + " התאמות ב־" + nfiles + " קבצים" + (total > CAP ? " (מוצגות " + CAP + " הראשונות, צמצמו עם סינון נתיב)" : "") : "";
    });
  }
  $(".cp-grepform", pane).addEventListener("submit", function (e) { e.preventDefault(); runGrep(); });
  var grepTimer;
  gq.addEventListener("input", function () { clearTimeout(grepTimer); grepTimer = setTimeout(runGrep, 250); });
  $$(".cp-opts input", pane).forEach(function (i) { i.addEventListener("change", runGrep); });
  $(".cp-where", pane).addEventListener("input", function () { clearTimeout(grepTimer); grepTimer = setTimeout(runGrep, 250); });
  gres.addEventListener("click", function (e) {
    var b = e.target.closest("[data-open]"); if (!b) return;
    var n = Number(b.dataset.ln || 0);
    // highlight what was searched for; a regex query is reduced to its literal part (\bNAME\b -> NAME)
    var term = $(".cp-regex", pane).checked ? gq.value.replace(/\\b/g, "") : gq.value;
    openFile(b.dataset.open, n, n, /^[\w֐-׿ .-]+$/.test(term) ? term : "");
  });
  // opts.regex / opts.caseSensitive set the checkboxes; a plain call clears them
  function openGrep(q, opts) {
    opts = opts || {};
    openPane("grep");
    $(".cp-regex", pane).checked = !!opts.regex;
    $(".cp-case", pane).checked = !!opts.caseSensitive;
    gq.value = q;
    runGrep();
  }

  /* ---------- link every file and symbol mention in the guide to the code ---------- */
  var PATH_RX = /^([\w.\/-]+\.(?:py|tsx?|sql|ya?ml|template|sh|md|txt|ini|json|html)|Makefile|\.env\.example)(?::(\d+)(?:[–-](\d+))?)?$/;
  var SYM_RX = /^@?([A-Za-z_][\w.]*)(?:\(\))?$/;
  var linked = 0, last = null;
  $$("main code").forEach(function (c) {
    if (c.closest("pre") || c.closest(".codelink")) return;
    var t = c.textContent.trim(), m = PATH_RX.exec(t), ref = null;
    var block = c.closest(".fx, li, p, td");
    if (m) {
      var f = resolvePath(m[1]);
      if (f) { ref = { path: f, line: Number(m[2] || 0), end: Number(m[3] || 0) }; last = { path: f, block: block }; }
    } else if ((m = /^:(\d+)$/.exec(t)) && last && last.block === block) {
      // ":238" right after a full path in the same sentence means the same file
      ref = { path: last.path, line: Number(m[1]), end: 0 };
    } else if ((m = SYM_RX.exec(t)) && t.length >= 4) {
      var name = m[1].split(".").pop(), d = name.length >= 4 && defOf(name);
      if (d) ref = { path: d[2], line: d[3], end: 0, sym: name };
    }
    if (!ref || ref.line > (IDX.files[ref.path] || 0)) return;
    c.classList.add("codelink");
    c.tabIndex = 0;
    c.setAttribute("role", "link");
    c.dataset.path = ref.path; c.dataset.line = ref.line; c.dataset.end = ref.end;
    c.title = "פתח בקוד: " + ref.path + (ref.line ? ":" + ref.line : "");
    linked++;
  });
  function follow(c) { openFile(c.dataset.path, Number(c.dataset.line), Number(c.dataset.end)); }
  document.addEventListener("click", function (e) {
    var c = e.target.closest && e.target.closest("code.codelink");
    if (c) {
      e.preventDefault();
      // Alt+click skips the viewer and opens the file in the local VS Code
      if (e.altKey) openInVSCode(c.dataset.path, Number(c.dataset.line)); else follow(c);
    }
    var g = e.target.closest && e.target.closest("[data-grep]");
    if (g) { e.preventDefault(); openGrep(g.dataset.grep); }
    var r = e.target.closest && e.target.closest("[data-reveal]");
    if (r && Guide.reveal) { e.preventDefault(); Guide.reveal(document.getElementById(r.dataset.reveal)); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.classList && e.target.classList.contains("codelink")) follow(e.target);
  });

  $$("[data-open-code]").forEach(function (b) { b.addEventListener("click", function () { openPane(b.dataset.openCode || "files"); }); });

  Guide.openFile = openFile;
  Guide.openGrep = openGrep;
  Guide.openPane = openPane;
  Guide.openInVSCode = openInVSCode;
  Guide.isTest = isTest;
  Guide.linkedCount = linked;
})();
