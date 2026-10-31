/* Timed practice: a random recipe as an exam task, with two hints and the full solution,
   all taken from the recipe's own markup. Results stay in this browser. Port of practice.js. */
import { useEffect, useMemo, useRef, useState } from "react";
import { recipes, type Recipe } from "../shared/content";
import HtmlContent from "../shared/HtmlContent";
import { openExam } from "../shared/nav";
import { persisted, useStore } from "../shared/store";

const TARGET_MIN = { easy: 8, med: 15, hard: 25 };
const LEVEL_LABEL = { easy: "קל", med: "בינוני", hard: "מתקדם" };
type Level = keyof typeof TARGET_MIN | "all";
interface Rec { tries: number; last: number; best: number; hints: number }
const practiceStore = persisted<Record<string, Rec>>("lolsuit-practice-v1", {});

const fmt = (sec: number) => `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
const target = (r: Recipe) => TARGET_MIN[r.level] * 60;

/* the recipe's parts: the first labelled block (where), its first diff (the change) */
function whereHtml(r: Recipe) {
  const tpl = document.createElement("template");
  tpl.innerHTML = r.html;
  const label = tpl.content.querySelector(".rlabel");
  if (!label) return "";
  let out = label.outerHTML;
  for (let n = label.nextElementSibling; n && !n.classList.contains("rlabel") && n.nodeName !== "PRE" && !n.querySelector("pre"); n = n.nextElementSibling) out += n.outerHTML;
  return out;
}
function changeHtml(r: Recipe) {
  const tpl = document.createElement("template");
  tpl.innerHTML = r.html;
  const pre = tpl.content.querySelector("pre");
  return pre ? pre.outerHTML : "<p>במתכון הזה אין diff, השינוי מתואר במילים. נסו את רמז 1 או את הפתרון.</p>";
}

export default function Practice() {
  const data = useStore(practiceStore);
  const [level, setLevel] = useState<Level>("all");
  const [task, setTask] = useState<Recipe | null>(null);
  const [started, setStarted] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [finished, setFinished] = useState<number | null>(null);
  const [hints, setHints] = useState<number[]>([]);
  const [checks, setChecks] = useState<boolean[]>([]);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!task || finished != null) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [task, finished]);

  const pick = (): Recipe | null => {
    const pool = recipes.filter((r) => level === "all" || r.level === level);
    if (!pool.length) return null;
    const fresh = pool.filter((r) => !data[r.id]);
    const from = fresh.length ? fresh : pool;
    let choice = from[Math.floor(Math.random() * from.length)];
    if (task && from.length > 1 && choice.id === task.id) choice = from.find((r) => r.id !== task.id)!;
    return choice;
  };
  const start = (r?: Recipe | null) => {
    const t = r || pick();
    if (!t) return;
    setTask(t); setStarted(Date.now()); setNow(Date.now()); setFinished(null); setHints([]); setChecks([]);
    setTimeout(() => box.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 0);
  };
  const finish = () => {
    if (!task || finished != null) return;
    const sec = Math.floor((Date.now() - started) / 1000);
    const used = hints.filter((h) => h < 3).length;
    practiceStore.set((d) => {
      const rec = d[task.id] || { tries: 0, last: 0, best: 0, hints: 0 };
      return { ...d, [task.id]: { tries: rec.tries + 1, last: sec, hints: used, best: !rec.best || sec < rec.best ? sec : rec.best } };
    });
    setFinished(sec);
  };
  const show = (k: number) => setHints((h) => h.includes(k) ? h : [...h, k]);

  const sec = task ? Math.floor(((finished != null ? started + finished * 1000 : now) - started) / 1000) : 0;
  const over = task ? sec > target(task) : false;
  const done = recipes.filter((r) => data[r.id]);
  const inTime = done.filter((r) => data[r.id].best <= target(r)).length;
  const weak = useMemo(() => recipes.filter((r) => data[r.id] && (data[r.id].best > target(r) || data[r.id].hints > 0)), [data]);

  return (
    <div className="practice">
      <div className="pr-controls">
        <div className="seg" role="group" aria-label="רמה">
          {(["all", "easy", "med", "hard"] as Level[]).map((l) => (
            <button key={l} type="button" aria-pressed={level === l} onClick={() => setLevel(l)}>{l === "all" ? "הכול" : LEVEL_LABEL[l]}</button>
          ))}
        </div>
        <button className="btn primary" type="button" onClick={() => start()}>משימה חדשה ▸</button>
        {weak.length > 0 && <button className="btn" type="button" onClick={() => start(weak[Math.floor(Math.random() * weak.length)])}>חזרה על משימה חלשה ({weak.length})</button>}
      </div>

      {task && (
        <div ref={box} className={"pr-task" + (over ? " over" : "") + (finished != null ? " finished" : "")}>
          <div className="pr-head">
            <span className={"tag " + task.level}>{LEVEL_LABEL[task.level]}</span>
            <span className="pr-timer">{fmt(sec)}</span>
            <span className="pr-target">יעד: {TARGET_MIN[task.level]} דקות</span>
          </div>
          <div className="pr-meter" aria-hidden="true"><i style={{ width: Math.min(100, 100 * sec / target(task)) + "%" }} /></div>
          <p className="pr-ask">הבוחן מבקש:</p>
          <h3 className="pr-title">{task.title}</h3>
          <p className="pr-brief">בצע את השינוי בפרויקט, הראה שהוא עובד, ותגיד מה עוד הוא משפיע עליו.</p>
          <div className="pr-actions">
            <button className="btn" type="button" onClick={() => show(1)}>רמז 1: איפה?</button>
            <button className="btn" type="button" onClick={() => show(2)}>רמז 2: מה משנים?</button>
            <button className="btn" type="button" onClick={() => { show(3); if (finished == null) setFinished(sec); }}>הצג פתרון מלא</button>
            <span className="grow" />
            <button className="btn primary" type="button" disabled={finished != null} onClick={finish}>✓ סיימתי</button>
            <button className="btn" type="button" onClick={() => start()}>דלג</button>
          </div>
          {finished != null && hints.indexOf(3) < 0 && (
            <div className="pr-result">סיימת ב־{fmt(finished)}{hints.length ? ` עם ${hints.length} רמזים` : " בלי רמזים"}{finished <= target(task) ? ". בזמן!" : ". מעל היעד. שווה לנסות שוב מאוחר יותר."}</div>
          )}
          <div className="pr-hints">
            {hints.map((k) => (
              <div key={k} className="pr-hint">
                <div className="pr-hint-title">{k === 1 ? "רמז 1: איפה" : k === 2 ? "רמז 2: השינוי" : "הפתרון המלא"}</div>
                <HtmlContent html={k === 1 ? whereHtml(task) : k === 2 ? changeHtml(task) : task.html} />
                {k === 3 && <button className="btn" type="button" onClick={() => openExam("/recipes?open=" + task.id)}>פתח את מתכון {task.num} בחלון המבחן ↗</button>}
              </div>
            ))}
          </div>
          <div className="pr-check">
            <b>לפני שלוחצים "סיימתי":</b>
            {["מצאתי את כל המקומות (חיפוש לערך עצמו, בלקוח ובשרת)", "אימתתי בדפדפן / curl / DevTools", "הרצתי את הטסטים הרלוונטיים", "git diff מראה רק את מה שהתכוונתי", "יודע להסביר מה עוד מושפע (דוקר, טסט, מקום כפול)"].map((c, i) => (
              <label key={i}><input type="checkbox" checked={!!checks[i]} onChange={(e) => setChecks((x) => { const y = [...x]; y[i] = e.target.checked; return y; })} /> {c}</label>
            ))}
          </div>
        </div>
      )}

      <div className="pr-history">
        <div className="pr-stats"><b>תרגלת {done.length} מתוך {recipes.length} משימות</b>
          {done.length > 0 && <> · {inTime} בזמן היעד <button className="btn" type="button" onClick={() => { if (window.confirm("למחוק את היסטוריית התרגול?")) practiceStore.set({}); }}>איפוס</button></>}
        </div>
        <div className="pr-chips">
          {recipes.map((r) => {
            const rec = data[r.id];
            return (
              <button key={r.id} type="button" className={"pr-chip" + (!rec ? "" : rec.best <= target(r) ? " ok" : " slow")} title={r.title} onClick={() => start(r)}>
                {r.num}{rec ? " · " + fmt(rec.best) : ""}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
