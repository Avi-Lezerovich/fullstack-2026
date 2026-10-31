/* The workbench: the task, the diff checker (tool 4), the verify checklist (tool 5),
   the git helper (tool 9) and all notes. */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import HtmlContent from "../../shared/HtmlContent";
import { recipes } from "../../shared/content";
import { indexStore, isTest, resolvePath } from "../../shared/code";
import { openFile } from "../../shared/pane";
import { useStore } from "../../shared/store";
import { copy } from "../../shared/toast";
import { openInVSCode } from "../../shared/vscode";
import { OpenAllButton, RefList, resolveRefs } from "../Refs";
import { changedFiles, checksStore, diffStore, notesStore, taskStore } from "../work";

interface Check { key: string; text: string; cmd?: string; why?: string }

/* tool 5: what to do so the change shows, and how to prove it, from the files involved */
function checklist(paths: string[]): Check[] {
  const has = (rx: RegExp) => paths.some((p) => rx.test(p));
  const out: Check[] = [];
  if (has(/^server\/(app\/|run\.py)/))
    out.push({ key: "srv", text: "להפעיל מחדש את השרת (אין reload אוטומטי)", cmd: "cd server\n.venv\\Scripts\\activate\npython run.py", why: "בדוקר: docker compose up --build -d server" });
  if (has(/^server\/worker\//) || has(/^server\/app\/(brain|services)\//))
    out.push({ key: "wrk", text: "להפעיל מחדש את ה־worker (הוא תהליך נפרד שמייבא את server/app)", cmd: "cd server\n.venv\\Scripts\\activate\npython run_worker.py", why: "בדוקר: docker compose up --build -d worker" });
  if (has(/^client\//))
    out.push({ key: "cli", text: "קליינט: לשמור, ו־HMR מעדכן לבד ב־5174 (בדוקר: --build ל־web)", cmd: "start http://localhost:5174", why: "לא מתעדכן? Ctrl+Shift+R" });
  if (has(/^database\/init\.sql$/))
    out.push({ key: "sql", text: "init.sql רץ רק על DB ריק: איפוס, או ALTER TABLE ידני", cmd: "docker compose down -v\ndocker compose up -d db", why: "שומרים נתונים: ALTER TABLE דרך mysql (בעמוד הפקודות)" });
  if (has(/config\.py$|^\.env|docker-compose\.yml$/))
    out.push({ key: "env", text: "שינוי config / .env / compose: restart לשרת ול־worker", cmd: "docker compose up -d server worker", why: "בדקו בעמוד המשתנים אם compose דורס את הערך" });
  if (has(/^server\//))
    out.push({ key: "pyt", text: "טסטים של השרת", cmd: "cd server\n.venv\\Scripts\\python -m pytest -m unit -q", why: "ואחר כך הכול: python -m pytest (צריך DB)" });
  if (has(/^client\//))
    out.push({ key: "npm", text: "טסטים ו־lint בקליינט", cmd: "cd client\nnpm run lint\nnpm test" });
  if (has(/\/tests\/|\.test\./)) out.push({ key: "tst", text: "שינית טסט: לוודא שהוא בודק את ההתנהגות החדשה ולא רק עובר" });
  out.push({ key: "dup", text: "חיפוש לערך הישן: לא נשאר עותק בלקוח/בשרת/בטסט", why: "בעמוד הקוד: שימושים, או git grep -n" });
  out.push({ key: "diff", text: "git diff מראה רק את מה שהתכוונתי", cmd: "git diff" });
  out.push({ key: "say", text: "יודע להסביר: איפה, מה עוד מושפע, ואיך הוכחתי" });
  return out;
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);

export default function Workbench() {
  const task = useStore(taskStore);
  const diff = useStore(diffStore);
  const checks = useStore(checksStore);
  const notes = useStore(notesStore);
  useStore(indexStore);

  const expected = useMemo(() => [...new Set(resolveRefs(task?.refs || []).map((r) => r.path))], [task]);
  const changed = useMemo(() => changedFiles(diff).map((p) => resolvePath(p) || p), [diff]);
  const unexpected = changed.filter((p) => !expected.includes(p));
  const untouched = expected.filter((p) => !changed.includes(p));
  const items = checklist([...new Set([...changed, ...expected])]);
  const tid = task?.id || "free";
  const done = items.filter((c) => checks[tid + ":" + c.key]).length;

  return (
    <div className="page work">
      <div className="page-head">
        <h1>שולחן עבודה <small>משימה → שינוי → הוכחה → git</small></h1>
      </div>

      <section className="panel">
        <div className="panel-head">
          <b>המשימה</b>
          <select className="search sel" value={task?.kind === "recipe" ? task.id : ""} aria-label="בחירת מתכון"
            onChange={(e) => {
              const r = recipes.find((x) => x.id === e.target.value);
              taskStore.set(r ? { kind: "recipe", id: r.id, title: `${r.num}. ${r.title}`, refs: r.refs, verifyHtml: r.verifyHtml } : null);
            }}>
            <option value="">{task && task.kind !== "recipe" ? 'מ"איפה זה?"' : "בחרו מתכון…"}</option>
            {recipes.map((r) => <option key={r.id} value={r.id}>{r.num}. {r.title}</option>)}
          </select>
          {task && <button className="btn sm" type="button" onClick={() => taskStore.set(null)}>נקה</button>}
        </div>
        {task ? <>
          <p className="task-title">{task.title}</p>
          <div className="row-actions">
            <OpenAllButton refs={task.refs} />
            <Link className="btn" to={(task.kind === "recipe" ? "/recipes?open=" : "/finder?open=") + task.id}>למקור</Link>
          </div>
          <RefList refs={task.refs} />
        </> : <p className="muted">בלי משימה הצ'קליסט נבנה רק מהקבצים ב־diff. בוחרים מתכון כאן, או "עובד על זה" בעמודים "איפה זה?" ו"מתכונים".</p>}
      </section>

      <div className="work-grid">
        <section className="panel">
          <div className="panel-head"><b>בודק diff</b>
            <button className="btn sm" type="button" onClick={() => copy("git status --short")}>העתק git status --short</button>
            <button className="btn sm" type="button" onClick={() => copy("git diff")}>העתק git diff</button>
          </div>
          <textarea className="diff-in" dir="ltr" spellCheck={false} value={diff} onChange={(e) => diffStore.set(e.target.value)}
            placeholder={"מדביקים כאן את הפלט של git status --short או git diff\n\n M server/app/security.py\n M client/src/pages/Signup.tsx"} />
          {changed.length > 0 ? (
            <ul className="diff-files">
              {changed.map((p) => (
                <li key={p} className={expected.includes(p) ? "ok" : task ? "warn" : ""}>
                  <span className="df-mark">{expected.includes(p) ? "✓" : task ? "?" : "•"}</span>
                  <button type="button" className="ref" onClick={() => openFile(p)}><code>{p}</code></button>
                  <button type="button" className="cp-vs" onClick={() => openInVSCode(p)}>VS</button>
                  {isTest(p) && <span className="t">טסט</span>}
                  {task && !expected.includes(p) && <span className="df-why">לא במשימה. בכוונה?</span>}
                </li>
              ))}
            </ul>
          ) : <p className="muted">עוד לא הודבק כלום.</p>}
          {task && changed.length > 0 && untouched.length > 0 && (
            <div className="df-missing">
              <b>במשימה ועוד לא שונו:</b>
              {untouched.map((p) => <div key={p}><button type="button" className="ref" onClick={() => openFile(p)}><code>{p}</code></button> <button type="button" className="cp-vs" onClick={() => openInVSCode(p)}>VS</button></div>)}
              <p className="muted small">לא כל קובץ במתכון חייב להשתנות (חלקם רק לבדיקה), אבל שווה לוודא.</p>
            </div>
          )}
          {task && changed.length > 0 && !unexpected.length && !untouched.length && <p className="ok-line">✓ ה־diff נוגע בדיוק בקבצים של המשימה.</p>}
        </section>

        <section className="panel">
          <div className="panel-head"><b>צ'קליסט אימות</b><span className="muted">{done}/{items.length}</span>
            <button className="btn sm" type="button" onClick={() => checksStore.set((c) => Object.fromEntries(Object.entries(c).filter(([k]) => !k.startsWith(tid + ":"))))}>איפוס</button>
          </div>
          <ul className="checks">
            {items.map((c) => {
              const k = tid + ":" + c.key;
              return (
                <li key={c.key} className={checks[k] ? "done" : ""}>
                  <label><input type="checkbox" checked={!!checks[k]} onChange={(e) => checksStore.set((x) => ({ ...x, [k]: e.target.checked }))} /> {c.text}</label>
                  {c.cmd && <button className="btn sm" type="button" title={c.cmd} onClick={() => copy(c.cmd!, "הפקודה")}>העתק פקודה</button>}
                  {c.why && <div className="muted small">{c.why}</div>}
                </li>
              );
            })}
          </ul>
          {task?.verifyHtml && <div className="verify-box"><b>איך מוכיחים (מהמתכון)</b><HtmlContent html={task.verifyHtml} /></div>}
          <div className="demo">
            <b>להתחברות:</b>
            <button className="btn sm" type="button" onClick={() => copy("dana@lolsuit.local")}>dana@lolsuit.local</button>
            <button className="btn sm" type="button" onClick={() => copy("admin@lolsuit.local")}>admin@lolsuit.local</button>
            <button className="btn sm" type="button" onClick={() => copy("demo1234")}>demo1234</button>
            <a className="btn sm" href="http://localhost:5174/" target="_blank" rel="noopener">האפליקציה ↗</a>
            <a className="btn sm" href="http://localhost:5174/login" target="_blank" rel="noopener">/login ↗</a>
            <a className="btn sm" href="http://localhost:5174/admin" target="_blank" rel="noopener">/admin ↗</a>
          </div>
        </section>
      </div>

      <GitHelper files={changed} title={task?.title || ""} />

      <section className="panel">
        <div className="panel-head"><b>כל ההערות</b><span className="muted">{notes.length}</span>
          {notes.length > 0 && <button className="btn sm" type="button" onClick={() => copy(notes.map((n) => `- ${n.text}${n.ref ? " (" + n.ref + ")" : ""}`).join("\n"), "ההערות")}>העתק הכל</button>}
          {notes.length > 0 && <button className="btn sm" type="button" onClick={() => { if (window.confirm("למחוק את כל ההערות?")) notesStore.set([]); }}>מחק הכל</button>}
        </div>
        {notes.length ? <ol className="notes-full">{notes.map((n) => (
          <li key={n.id}><span className="tm-when">{new Date(n.at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}</span> {n.text}
            {n.ref && <button type="button" className="ref" onClick={() => { const [p, l] = n.ref!.split(":"); openFile(p, Number(l || 0)); }}><code>{n.ref}</code></button>}</li>
        ))}</ol> : <p className="muted">מוסיפים הערות מהשעון בפינה (✎).</p>}
      </section>
    </div>
  );
}

/* tool 9: branch, add, commit and push lines, filled from the task and the diff */
function GitHelper({ files, title }: { files: string[]; title: string }) {
  const [type, setType] = useState("feat");
  const [scope, setScope] = useState("");
  const [msg, setMsg] = useState("");
  const [branch, setBranch] = useState("");
  const guessScope = files.some((f) => f.startsWith("client/")) && files.some((f) => f.startsWith("server/")) ? "" : files.some((f) => f.startsWith("client/")) ? "client" : files.some((f) => f.startsWith("server/")) ? "server" : "";
  const sc = scope || guessScope;
  const subject = msg || "describe the change";
  const br = branch || `${type === "feat" ? "feature" : type}/${slug(msg) || "exam-change"}`;
  const add = files.length ? "git add " + files.map((f) => (/\s/.test(f) ? `"${f}"` : f)).join(" ") : "git add .";
  const block = [`git switch -c ${br}`, add, `git commit -m "${type}${sc ? `(${sc})` : ""}: ${subject.replace(/"/g, "'")}"`, `git push -u origin ${br}`].join("\n");
  return (
    <section className="panel">
      <div className="panel-head"><b>git: לשמור ולשלוח</b>{title && <span className="muted">{title}</span>}</div>
      <div className="git-form">
        <label>סוג <select className="search sel" value={type} onChange={(e) => setType(e.target.value)}>
          {["feat", "fix", "refactor", "style", "test", "docs", "chore"].map((t) => <option key={t}>{t}</option>)}
        </select></label>
        <label>scope <input className="search" dir="ltr" value={scope} placeholder={guessScope || "(ריק)"} onChange={(e) => setScope(e.target.value)} /></label>
        <label className="grow">הודעה (באנגלית) <input className="search" dir="ltr" value={msg} placeholder="raise the minimum password length to 10" onChange={(e) => setMsg(e.target.value)} /></label>
        <label>ענף <input className="search" dir="ltr" value={branch} placeholder={br} onChange={(e) => setBranch(e.target.value)} /></label>
      </div>
      <div className="codebox"><pre><code>{block}</code></pre><button className="copy" type="button" onClick={() => copy(block, "פקודות git")}>העתק</button></div>
      <div className="row-actions">
        {block.split("\n").map((l, i) => <button key={i} className="btn sm" type="button" onClick={() => copy(l)}>{["ענף", "add", "commit", "push"][i]}</button>)}
        <button className="btn sm" type="button" onClick={() => copy("git diff --stat")}>git diff --stat</button>
        <button className="btn sm" type="button" onClick={() => copy("git stash")}>git stash</button>
        <button className="btn sm" type="button" onClick={() => copy(files.length ? "git restore " + files.join(" ") : "git restore .")}>לבטל (git restore)</button>
      </div>
      {!files.length && <p className="muted small">בלי diff מודבק, add הוא git add . — הדביקו את git status --short בבודק כדי להוסיף רק את הקבצים שלכם.</p>}
    </section>
  );
}
