/* The top bar both windows share: brand, the window's own nav, quick find, code, theme,
   and a button to the other window. */
import { useEffect, type ReactNode } from "react";
import { persisted, useStore } from "./store";
import { indexStore, loadIndex } from "./code";
import { openPane } from "./pane";
import { Toast } from "./toast";
import { ZoomDialog } from "./Zoom";

const themeStore = persisted<"light" | "dark" | "">("lolsuit-theme", "");
function applyTheme(t: string) {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
applyTheme(themeStore.get());

export function useBoot() {
  useEffect(() => { loadIndex(); }, []);
}

export default function Shell({ kind, sub, nav, right, children }: {
  kind: "study" | "exam"; sub: string; nav?: ReactNode; right?: ReactNode; children: ReactNode;
}) {
  const theme = useStore(themeStore);
  const idx = useStore(indexStore);
  useEffect(() => applyTheme(theme), [theme]);
  const toggle = () => {
    const cur = theme || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    themeStore.set(cur === "dark" ? "light" : "dark");
  };
  return (
    <div className={"app app-" + kind}>
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
        <defs>
          <marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path className="ah" d="M0,0 L10,5 L0,10 z" /></marker>
          <marker id="arwA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path className="ah acc" d="M0,0 L10,5 L0,10 z" /></marker>
          <marker id="arwW" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path className="ah warn" d="M0,0 L10,5 L0,10 z" /></marker>
          <marker id="arwO" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path className="ah ok" d="M0,0 L10,5 L0,10 z" /></marker>
        </defs>
      </svg>
      <header className="bar">
        <img className="seal-img" src="img/lolsuit-seal.svg" alt="" width="34" height="34" />
        <div className="name">LolSuit<small>{sub}</small></div>
        {nav}
        <div className="grow" />
        <button className="iconbtn tool-btn" type="button" title="חיפוש מהיר (Ctrl+K)" onClick={() => window.dispatchEvent(new CustomEvent("open-palette"))}>
          ⌕ <span className="lbl">חיפוש</span> <kbd>Ctrl K</kbd>
        </button>
        <button className="iconbtn tool-btn" type="button" title="צפייה בקוד הפרויקט" onClick={() => openPane("files")}>&lt;/&gt; <span className="lbl">קוד</span></button>
        {right}
        <button className="iconbtn" type="button" title="מצב כהה/בהיר" aria-label="החלפת מצב כהה/בהיר" onClick={toggle}>◐</button>
      </header>
      {children}
      <footer className="site-foot">
        <div className="foot-in">
          <div className="foot-brand"><img src="img/lolsuit-seal.svg" alt="" width="28" height="28" /><span>LolSuit</span></div>
          <p className="foot-cap">Full-Stack @ RUNI · 2026 · צילום הקוד: commit {idx.commit || "…"} · <a href="https://github.com/Avi-Lezerovich/fullstack-2026">GitHub</a></p>
        </div>
      </footer>
      <Toast />
      <ZoomDialog />
    </div>
  );
}
