/* LolSuit study guide — offline: registers sw.js and says, in the sidebar, whether the
   whole guide (code snapshot included) is saved on this computer. */
(function () {
  "use strict";
  var out = document.getElementById("offlineState");
  function say(text, ok) {
    if (!out) return;
    out.textContent = text;
    out.classList.toggle("ok", !!ok);
  }
  if (!("serviceWorker" in navigator) || !window.caches) { say("הדפדפן הזה לא שומר את האתר לעבודה בלי אינטרנט."); return; }
  if (location.protocol === "file:") { say("פתחו דרך http כדי שהאתר יישמר לעבודה בלי אינטרנט."); return; }

  function check() {
    return caches.keys().then(function (keys) {
      var saved = keys.some(function (k) { return /^lolsuit-guide-(?!runtime)/.test(k); });
      if (saved && navigator.serviceWorker.controller) say("✓ האתר שמור במחשב, ועובד גם בלי אינטרנט", true);
      else if (saved) say("✓ נשמר. רעננו פעם אחת כדי שגם הפונטים יישמרו", true);
      else say("שומר את האתר לעבודה בלי אינטרנט…");
      return saved;
    });
  }
  say("שומר את האתר לעבודה בלי אינטרנט…");
  navigator.serviceWorker.register("sw.js").then(function (reg) {
    navigator.serviceWorker.ready.then(check);
    reg.addEventListener("updatefound", function () {
      var w = reg.installing;
      if (w) w.addEventListener("statechange", function () { if (w.state === "activated") check(); });
    });
  }).catch(function () { say("לא הצלחתי לשמור את האתר לעבודה בלי אינטרנט."); });
  window.addEventListener("online", check);
  window.addEventListener("offline", function () { say("אין אינטרנט כרגע. עובדים מהעותק השמור", true); });
})();
