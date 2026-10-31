/* Tool 8: a draggable clock with notes, on every page of the exam window. */
import { useEffect, useRef, useState } from "react";
import { useStore } from "../shared/store";
import { paneStore } from "../shared/pane";
import { addNote, clockSeconds, clockStore, notesStore, timerUiStore } from "./work";

export const fmtClock = (sec: number) => {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + ":" : "") + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
};

export function useTick(on: boolean) {
  const [, set] = useState(0);
  useEffect(() => { if (!on) return; const t = setInterval(() => set((x) => x + 1), 1000); return () => clearInterval(t); }, [on]);
}

export function startPause() {
  clockStore.set((c) => c.running ? { ...c, running: false, elapsed: c.elapsed + Date.now() - c.startedAt } : { ...c, running: true, startedAt: Date.now() });
}
export function resetClock() {
  clockStore.set((c) => ({ ...c, running: false, elapsed: 0, startedAt: 0 }));
}

export default function Timer() {
  const c = useStore(clockStore);
  const ui = useStore(timerUiStore);
  const notes = useStore(notesStore);
  const pane = useStore(paneStore);
  useTick(c.running);
  const [text, setText] = useState("");
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const sec = clockSeconds(c);
  const over = c.targetMin > 0 && sec > c.targetMin * 60;
  const curRef = pane.open && pane.tab === "file" && pane.path ? pane.path + (pane.line ? ":" + pane.line : "") : "";

  const onDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button, input, select, textarea")) return;
    drag.current = { x: e.clientX, y: e.clientY, ox: ui.x, oy: ui.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    // anchored bottom-left: moving right grows x, moving down shrinks y
    const x = Math.max(4, Math.min(window.innerWidth - 120, d.ox + (e.clientX - d.x)));
    const y = Math.max(4, Math.min(window.innerHeight - 60, d.oy - (e.clientY - d.y)));
    timerUiStore.set((u) => ({ ...u, x, y }));
  };

  return (
    <div className={"timer" + (ui.open ? " open" : "") + (over ? " over" : "") + (c.running ? " running" : "")}
      style={{ left: ui.x, bottom: ui.y }} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => { drag.current = null; }}>
      <div className="tm-row">
        <span className="tm-grip" title="גררו כדי להזיז" aria-hidden="true">⠿</span>
        <span className="tm-time" title={c.targetMin ? `יעד: ${c.targetMin} דקות` : ""}>{fmtClock(sec)}</span>
        <button type="button" className="tm-btn" onClick={startPause} aria-label={c.running ? "השהה" : "התחל"}>{c.running ? "❚❚" : "▶"}</button>
        <button type="button" className="tm-btn" onClick={() => { if (!sec || window.confirm("לאפס את השעון?")) resetClock(); }} aria-label="אפס">↺</button>
        <button type="button" className="tm-btn" onClick={() => timerUiStore.set((u) => ({ ...u, open: !u.open }))} aria-label="הערות">{ui.open ? "▾" : "✎"}{notes.length ? <sup>{notes.length}</sup> : null}</button>
      </div>
      {c.targetMin > 0 && <div className="tm-bar" aria-hidden="true"><i style={{ width: Math.min(100, 100 * sec / (c.targetMin * 60)) + "%" }} /></div>}
      {ui.open && (
        <div className="tm-notes">
          <div className="tm-target">
            יעד:
            {[0, 15, 30, 45, 60, 90].map((m) => (
              <button key={m} type="button" className={"tm-chip" + (c.targetMin === m ? " on" : "")} onClick={() => clockStore.set((x) => ({ ...x, targetMin: m }))}>{m ? m + "′" : "בלי"}</button>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); addNote(text); setText(""); }}>
            <input className="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="הערה: מה עשיתי / מה נשאר" aria-label="הערה חדשה" />
          </form>
          {curRef && <button type="button" className="btn tm-ref" onClick={() => { addNote(text, curRef); setText(""); }}>＋ הערה עם {curRef.split("/").pop()}</button>}
          <ol className="tm-list">
            {notes.slice().reverse().slice(0, 8).map((n) => (
              <li key={n.id}>
                <span className="tm-when">{new Date(n.at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}</span>
                <span>{n.text}{n.ref && <code> {n.ref}</code>}</span>
                <button type="button" aria-label="מחק" onClick={() => notesStore.set((all) => all.filter((x) => x.id !== n.id))}>✕</button>
              </li>
            ))}
          </ol>
          {notes.length > 8 && <div className="tm-more">ועוד {notes.length - 8} בשולחן העבודה</div>}
        </div>
      )}
    </div>
  );
}
