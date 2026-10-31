/* Tool 7: is the local stack up? An opaque no-cors fetch resolves when something answers on
   the port and rejects when nothing listens. The page cannot read the body (CORS), so the
   database light links to /api/health instead of guessing. */
import { useEffect, useState } from "react";
import { copy } from "../shared/toast";

interface Probe { id: string; label: string; url: string; open: string; start: string; startNote: string }
const PROBES: Probe[] = [
  { id: "api", label: "שרת API · 5002", url: "http://localhost:5002/api/health", open: "http://localhost:5002/api/health", start: "cd server\n.venv\\Scripts\\activate\npython run.py", startNote: "טרמינל חדש מתיקיית הפרויקט" },
  { id: "web", label: "קליינט · 5174", url: "http://localhost:5174/", open: "http://localhost:5174/", start: "cd client\nnpm run dev", startNote: "טרמינל חדש מתיקיית הפרויקט" },
  { id: "docker", label: "דוקר (nginx) · 8080", url: "http://localhost:8080/", open: "http://localhost:8080/", start: "docker compose up --build -d", startNote: "רק אם עובדים בדוקר" },
];
type State = "up" | "down" | "checking";

async function probe(url: string): Promise<boolean> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 2500);
  try { await fetch(url, { mode: "no-cors", cache: "no-store", signal: ctl.signal }); return true; }
  catch { return false; }
  finally { clearTimeout(t); }
}

export default function Status({ compact = false }: { compact?: boolean }) {
  const [st, setSt] = useState<Record<string, State>>({});
  const [at, setAt] = useState<Date | null>(null);
  const run = async () => {
    setSt((s) => Object.fromEntries(PROBES.map((p) => [p.id, s[p.id] || "checking"])));
    const res = await Promise.all(PROBES.map((p) => probe(p.url)));
    setSt(Object.fromEntries(PROBES.map((p, i) => [p.id, res[i] ? "up" : "down"])));
    setAt(new Date());
  };
  useEffect(() => {
    run();
    const t = setInterval(() => { if (document.visibilityState === "visible") run(); }, 10000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className={"status-panel" + (compact ? " compact" : "")}>
      <div className="sp-head">
        <b>מה רץ עכשיו</b>
        <span className="sp-at">{at ? "נבדק ב־" + at.toLocaleTimeString("he-IL") : "בודק…"}</span>
        <button className="btn sm" type="button" onClick={run}>בדוק שוב</button>
      </div>
      <ul className="lights">
        {PROBES.map((p) => {
          const s = st[p.id] || "checking";
          return (
            <li key={p.id} className={"light " + s}>
              <span className="dot" aria-hidden="true" />
              <span className="lt-label">{p.label}</span>
              <span className="lt-state">{s === "up" ? "רץ" : s === "down" ? "לא עונה" : "…"}</span>
              <a className="btn sm" href={p.open} target="_blank" rel="noopener">פתח ↗</a>
              {s === "down" && !compact && <button className="btn sm" type="button" title={p.startNote} onClick={() => copy(p.start, "פקודת ההפעלה")}>העתק פקודת הפעלה</button>}
            </li>
          );
        })}
        <li className="light info">
          <span className="dot" aria-hidden="true" />
          <span className="lt-label">MySQL · 3307 ו־worker</span>
          <span className="lt-state">ב־/api/health: database, worker.seconds_since_tick</span>
          <a className="btn sm" href="http://localhost:5002/api/health" target="_blank" rel="noopener">health ↗</a>
          {!compact && <button className="btn sm" type="button" onClick={() => copy("docker compose up -d db", "פקודת ה־DB")}>העתק: הרמת DB</button>}
        </li>
      </ul>
      {!compact && <p className="sp-note">הבדיקה רק שואלת אם משהו עונה בפורט. אם הדפדפן שואל אם לאפשר גישה ל"מכשירים ברשת המקומית", מאשרים. זה רק בשביל הנורות.</p>}
    </div>
  );
}
