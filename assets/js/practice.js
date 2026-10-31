/* LolSuit study guide — practice: a random recipe as an exam task, with a timer, two hints
   and the full solution, all taken from the recipe's own markup. Results stay in this browser. */
(function () {
  "use strict";
  var Guide = window.Guide = window.Guide || {};
  var root = document.getElementById("practice");
  if (!root) return;
  function $(sel, r) { return (r || document).querySelector(sel); }
  function $$(sel, r) { return Array.prototype.slice.call((r || document).querySelectorAll(sel)); }

  var STORE = "lolsuit-practice-v1";
  var TARGET_MIN = { easy: 8, med: 15, hard: 25 };
  var LEVEL_LABEL = { easy: "קל", med: "בינוני", hard: "מתקדם" };
  function load() { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch (e) { return {}; } }
  function save(data) { try { localStorage.setItem(STORE, JSON.stringify(data)); } catch (e) { /* storage blocked */ } }

  // every recipe, as a task
  var tasks = $$("details.recipe").map(function (d) {
    var tag = $("summary .tag", d), level = tag ? (tag.classList.contains("hard") ? "hard" : tag.classList.contains("med") ? "med" : "easy") : "easy";
    var title = $("summary", d).textContent.replace(/^\s*(קל|בינוני|מתקדם)\s*/, "").replace(/^\d+\.\s*/, "").trim();
    return { id: d.id, el: d, level: level, title: title, num: d.id.replace(/^r/, "") };
  });

  var level = "all", task = null, started = 0, timer = null, hints = 0;
  var box = $("#prTask"), out = $("#prHints");

  function fmt(sec) { var m = Math.floor(sec / 60), s = sec % 60; return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s; }
  function tick() {
    var sec = Math.floor((Date.now() - started) / 1000), target = TARGET_MIN[task.level] * 60;
    $("#prTimer").textContent = fmt(sec);
    $("#prBar").style.width = Math.min(100, 100 * sec / target) + "%";
    box.classList.toggle("over", sec > target);
  }
  function stop() { clearInterval(timer); timer = null; }

  // A recipe's parts: the first labelled block (files / where), its first code block (the change), all of it (solution).
  function cleanClone(node) {
    var c = node.cloneNode(true);
    $$("button.copy", c).forEach(function (b) { b.remove(); });
    return c;
  }
  function whereHint(t) {
    var inner = $(".in", t.el), frag = document.createDocumentFragment(), label = $(".rlabel", inner);
    if (!label) return frag;
    frag.appendChild(cleanClone(label));
    for (var n = label.nextElementSibling; n && !n.classList.contains("rlabel") && !n.querySelector("pre") && n.nodeName !== "PRE"; n = n.nextElementSibling) {
      frag.appendChild(cleanClone(n));
    }
    return frag;
  }
  function changeHint(t) {
    var pre = $(".in pre", t.el);
    var wrap = document.createElement("div");
    if (pre) wrap.appendChild(cleanClone(pre));
    else wrap.textContent = "במתכון הזה אין diff, השינוי מתואר במילים. נסו את רמז 1 או את הפתרון.";
    return wrap;
  }
  function showHint(kind) {
    var block = document.createElement("div");
    block.className = "pr-hint";
    var h = document.createElement("div"); h.className = "pr-hint-title";
    if (kind === 1) { h.textContent = "רמז 1: איפה"; block.appendChild(h); block.appendChild(whereHint(task)); }
    else if (kind === 2) { h.textContent = "רמז 2: השינוי"; block.appendChild(h); block.appendChild(changeHint(task)); }
    else {
      h.textContent = "הפתרון המלא";
      block.appendChild(h);
      block.appendChild(cleanClone($(".in", task.el)));
      var go = document.createElement("a");
      go.href = "#" + task.id; go.textContent = "פתח את מתכון " + task.num + " במדריך ←";
      go.addEventListener("click", function (e) { e.preventDefault(); if (Guide.reveal) Guide.reveal(task.el); });
      block.appendChild(go);
    }
    var old = $('.pr-hint[data-k="' + kind + '"]', out);
    if (old) old.remove(); else hints++;
    block.dataset.k = kind;
    out.appendChild(block);
    block.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function pick() {
    var pool = tasks.filter(function (t) { return level === "all" || t.level === level; });
    if (!pool.length) return null;
    var done = load(), fresh = pool.filter(function (t) { return !done[t.id]; });
    var from = fresh.length ? fresh : pool;
    var choice = from[Math.floor(Math.random() * from.length)];
    if (task && from.length > 1 && choice.id === task.id) return pick();
    return choice;
  }
  function start(t) {
    stop();
    task = t || pick();
    if (!task) return;
    hints = 0; out.innerHTML = "";
    $$(".pr-check input", box).forEach(function (c) { c.checked = false; });
    var tag = $("#prTag");
    tag.className = "tag " + task.level; tag.textContent = LEVEL_LABEL[task.level];
    $("#prTitle").textContent = task.title;
    $("#prTarget").textContent = "יעד: " + TARGET_MIN[task.level] + " דקות";
    box.hidden = false; box.classList.remove("over", "finished");
    started = Date.now(); tick(); timer = setInterval(tick, 1000);
    box.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function finish() {
    if (!task || !timer) return;
    stop();
    var sec = Math.floor((Date.now() - started) / 1000), data = load(), rec = data[task.id] || { tries: 0 };
    rec.tries++; rec.last = sec; rec.hints = hints;
    if (!rec.best || sec < rec.best) rec.best = sec;
    data[task.id] = rec; save(data);
    box.classList.add("finished");
    var msg = document.createElement("div");
    msg.className = "pr-result";
    msg.textContent = "סיימת ב־" + fmt(sec) + (hints ? " עם " + hints + " רמזים" : " בלי רמזים") +
      (sec <= TARGET_MIN[task.level] * 60 ? ". בזמן!" : ". מעל היעד. שווה לנסות שוב מאוחר יותר.");
    out.insertBefore(msg, out.firstChild);
    renderHistory();
  }

  function renderHistory() {
    var data = load(), done = tasks.filter(function (t) { return data[t.id]; });
    var html = '<div class="pr-stats"><b>תרגלת ' + done.length + " מתוך " + tasks.length + " משימות</b>";
    if (done.length) {
      var inTime = done.filter(function (t) { return data[t.id].best <= TARGET_MIN[t.level] * 60; }).length;
      html += " · " + inTime + " בזמן היעד" + ' <button class="btn" type="button" id="prReset">איפוס</button>';
    }
    html += '</div><div class="pr-chips">';
    html += tasks.map(function (t) {
      var r = data[t.id], cls = !r ? "" : r.best <= TARGET_MIN[t.level] * 60 ? " ok" : " slow";
      return '<button type="button" class="pr-chip' + cls + '" data-task="' + t.id + '" title="' + t.title.replace(/"/g, "&quot;") + '">' +
        t.num + (r ? " · " + fmt(r.best) : "") + "</button>";
    }).join("");
    $("#prHistory").innerHTML = html + "</div>";
  }

  $("#prLevel").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    level = b.dataset.level;
    $$("#prLevel button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
  });
  $("#prNew").addEventListener("click", function () { start(); });
  $("#prHint1").addEventListener("click", function () { if (task) showHint(1); });
  $("#prHint2").addEventListener("click", function () { if (task) showHint(2); });
  $("#prSolve").addEventListener("click", function () { if (task) { stop(); showHint(3); } });
  $("#prDone").addEventListener("click", finish);
  $("#prSkip").addEventListener("click", function () { start(); });
  $("#prHistory").addEventListener("click", function (e) {
    var c = e.target.closest("[data-task]");
    if (c) { start(tasks.filter(function (t) { return t.id === c.dataset.task; })[0]); return; }
    if (e.target.id === "prReset" && window.confirm("למחוק את היסטוריית התרגול?")) { save({}); renderHistory(); }
  });
  renderHistory();
  Guide.practice = start;
})();
