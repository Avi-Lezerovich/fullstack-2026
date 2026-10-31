import { Link } from "react-router-dom";
import HtmlContent from "../../shared/HtmlContent";
import { finderIntroHtml } from "../../shared/content";
import { useStore } from "../../shared/store";
import { indexStore } from "../../shared/code";
import { copy } from "../../shared/toast";
import Status from "../Status";
import { notesStore, taskStore, clockStore, clockSeconds } from "../work";
import { fmtClock, startPause, useTick } from "../Timer";
import { OpenAllButton } from "../Refs";

export default function Dashboard() {
  const task = useStore(taskStore);
  const notes = useStore(notesStore);
  const clock = useStore(clockStore);
  const idx = useStore(indexStore);
  useTick(clock.running);
  return (
    <div className="page dash">
      <section className="hero">
        <div>
          <h1>חלון מבחן</h1>
          <p>מקבלים משימה → מוצאים איפה → פותחים ב־VS Code → משנים → מוכיחים. כל מה שצריך בדרך נמצא כאן, וגם עובד בלי אינטרנט.</p>
        </div>
        <button className="hero-search" type="button" onClick={() => window.dispatchEvent(new CustomEvent("open-palette"))}>
          <span>⌕ מה ביקשו לשנות? סיסמה, צבע, endpoint, פקודה…</span><kbd>Ctrl K</kbd>
        </button>
        <div className="hero-actions">
          <button className="btn primary" type="button" onClick={startPause}>{clock.running ? "❚❚ השהה שעון" : "▶ התחל שעון"} · {fmtClock(clockSeconds(clock))}</button>
          <button className="btn" type="button" onClick={() => copy("git status", "git status")}>העתק git status</button>
          <span className="hero-meta">צילום הקוד: commit <code>{idx.commit || "…"}</code></span>
        </div>
      </section>

      <div className="dash-grid">
        <Status />

        <section className="panel">
          <div className="panel-head"><b>המשימה שלי</b><Link to="/work" className="btn sm">שולחן עבודה ←</Link></div>
          {task ? <>
            <p className="task-title">{task.title}</p>
            <div className="row-actions"><OpenAllButton refs={task.refs} /><Link className="btn" to={(task.kind === "recipe" ? "/recipes?open=" : "/finder?open=") + task.id}>למקור</Link></div>
          </> : <p className="muted">עוד לא נבחרה משימה. ב"איפה זה?" או ב"מתכונים" לוחצים <b>עובד על זה</b>, והקבצים, הצ'קליסט וה־diff מתחברים אליה.</p>}
          <div className="panel-head" style={{ marginTop: 14 }}><b>הערות אחרונות</b></div>
          {notes.length ? <ul className="mini-notes">{notes.slice(-4).reverse().map((n) => <li key={n.id}>{n.text}{n.ref && <code> {n.ref}</code>}</li>)}</ul>
            : <p className="muted">ההערות מהשעון (בפינה) יופיעו כאן.</p>}
        </section>

        <section className="panel span2">
          <div className="panel-head"><b>קיצורי דרך</b></div>
          <div className="tiles">
            <Link className="tile" to="/finder"><b>⌖ איפה זה?</b><span>ביקשו לשנות X: קובץ, שורה, ומה עוד לעדכן</span></Link>
            <Link className="tile" to="/recipes"><b>☰ מתכונים</b><span>25 שינויים נפוצים, צעד אחר צעד, עם diff</span></Link>
            <Link className="tile" to="/flows"><b>⇄ זרימות</b><span>כפתור → api.ts → route → service → טבלה</span></Link>
            <Link className="tile" to="/code"><b>&lt;/&gt; קוד ושימושים</b><span>חיפוש בכל הקוד, ואיפה עוד משתמשים בשם</span></Link>
            <Link className="tile" to="/commands"><b>›_ פקודות</b><span>הרצה, טסטים, git, curl, MySQL</span></Link>
            <Link className="tile" to="/env"><b>⚙ משתנים ופורטים</b><span>איפה כל משתנה סביבה מוגדר ונקרא</span></Link>
            <Link className="tile" to="/trouble"><b>⚠ תקלות</b><span>השינוי לא מופיע? השרת לא עולה?</span></Link>
            <Link className="tile" to="/work"><b>✎ שולחן עבודה</b><span>בודק diff, צ'קליסט אימות, git</span></Link>
          </div>
        </section>
      </div>

      <HtmlContent className="exam-intro" html={finderIntroHtml} />
    </div>
  );
}
