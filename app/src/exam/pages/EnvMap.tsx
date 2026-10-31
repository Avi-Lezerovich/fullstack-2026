/* Tool 6: every environment variable — default in config.py, .env.example, both compose
   files, and who reads it — with the mismatches that bite (compose overrides the code
   default; a variable missing from compose never reaches the container). */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { norm } from "../../shared/Palette";
import { openFile } from "../../shared/pane";
import { useStore } from "../../shared/store";
import { copy } from "../../shared/toast";
import { openInVSCode } from "../../shared/vscode";
import { mapsStore, type EnvVar } from "../maps";

const PORTS: [string, string, string, string][] = [
  ["Vite dev (קליינט)", "5174", "client/vite.config.ts", "npm run dev · proxy של /api ל־5002"],
  ["API (Flask)", "5002", "server/app/config.py", "PORT; בדוקר מפורסם רק ל־127.0.0.1"],
  ["MySQL", "3307 → 3306", "docker-compose.yml", "DB_PUBLISH_PORT; בתוך דוקר השרת מדבר עם db:3306"],
  ["web (nginx, דוקר)", "8080", "docker-compose.yml", "WEB_PUBLISH_PORT; מגיש את הקליינט ומעביר /api"],
  ["ייצור (EC2)", "80", "prod/docker-compose.yml", "רק web מפורסם; השרת לא"],
];

/* literal defaults only: "False" ~ "0", quotes dropped; anything computed returns null */
function lit(v: string | null | undefined): string | null {
  if (v == null) return null;
  const s = v.trim().replace(/^["']|["']$/g, "");
  if (/^(False|false|0)$/.test(s)) return "0";
  if (/^(True|true|1)$/.test(s)) return "1";
  if (/^[\w.:/@-]*$/.test(s)) return s;
  return null;
}

function issues(v: EnvVar): string[] {
  const out: string[] = [];
  if (v.code && !v.compose) out.push("לא מועבר בדוקר: שינוי ב־.env לא יגיע לקונטיינר");
  const a = lit(v.code?.default), b = lit(v.compose?.default);
  if (v.code && v.compose && a != null && b != null && a !== b && v.compose.default !== null) out.push(`compose דורס: בקוד ${v.code.default || '""'}, בדוקר ${v.compose.default || '""'}`);
  if (v.prod?.required) out.push("חובה בייצור (${VAR:?})");
  if (!v.code && (v.compose || v.prod) && !/^(MYSQL_|DOCKERHUB|TAG$|.*_PUBLISH_|API_UPSTREAM|WEB_PUBLISH|.*_MEMORY_LIMIT|GUNICORN_|AWS_|GEMINI_KEY)/.test(v.name)) out.push("רק ב־compose, לא נקרא ישירות ב־config.py");
  return out;
}

function Loc({ file, line, label }: { file: string; line: number; label?: string }) {
  return (
    <span className="loc">
      <button type="button" className="ref" onClick={() => openFile(file, line)}><code>{label || `${file.split("/").pop()}:${line}`}</code></button>
      <button type="button" className="cp-vs" onClick={() => openInVSCode(file, line)}>VS</button>
    </span>
  );
}

export default function EnvMap() {
  const maps = useStore(mapsStore);
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const toks = norm(q).split(" ").filter(Boolean);
  const list = useMemo(() => (maps?.env || []).filter((v) => {
    if (onlyIssues && !issues(v).length) return false;
    const h = norm(v.name + " " + (v.field || "") + " " + v.readers.map((r) => r.file).join(" "));
    return toks.every((t) => h.includes(t));
  }), [maps, q, onlyIssues]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="page">
      <div className="page-head">
        <h1>משתנים ופורטים <small>איפה כל ערך מוגדר, ומי קורא אותו</small></h1>
        <p>סדר העדיפות: משתנה שמוגדר ב־<code>environment</code> של compose <b>דורס</b> את ברירת המחדל ב־<code>config.py</code>. משתנה שלא מופיע ב־compose לא מגיע לקונטיינר בכלל, גם אם הוא ב־<code>.env</code>. בהרצה מקומית (<code>python run.py</code>) קובע <code>.env</code> ואז ברירת המחדל בקוד.</p>
      </div>

      <section className="panel">
        <div className="panel-head"><b>פורטים</b></div>
        <div className="tablewrap"><table>
          <thead><tr><th>מה</th><th>פורט</th><th>איפה מוגדר</th><th>הערה</th></tr></thead>
          <tbody>{PORTS.map(([what, port, file, note]) => (
            <tr key={what}><td>{what}</td><td><code>{port}</code></td><td><Loc file={file} line={0} label={file} /></td><td>{note}</td></tr>
          ))}</tbody>
        </table></div>
      </section>

      <div className="filter-bar sticky">
        <input className="search big" type="search" placeholder="סינון: PHASE, SMTP, UPLOAD, worker, mail…" aria-label="סינון משתנים" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="chk-inline"><input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} /> רק עם אזהרה</label>
        <span className="count">{list.length} משתנים</span>
      </div>
      {!maps ? <p className="muted">טוען…</p> : (
        <div className="tablewrap env-table"><table>
          <thead><tr><th>משתנה</th><th>config.py (ברירת מחדל)</th><th>.env.example</th><th>docker-compose.yml</th><th>prod</th><th>נקרא ב־</th></tr></thead>
          <tbody>
            {list.map((v) => {
              const warn = issues(v);
              return (
                <tr key={v.name} className={warn.length ? "warn" : ""}>
                  <td>
                    <button type="button" className="env-name" title="העתק" onClick={() => copy(v.name)}><code>{v.name}</code></button>
                    {v.field && <div className="muted small">settings.{v.field}</div>}
                    {warn.map((w) => <div key={w} className="env-warn">⚠ {w}</div>)}
                  </td>
                  <td>{v.code ? <><code>{v.code.default || '""'}</code> <span className="muted small">{v.code.kind}</span><br /><Loc file="server/app/config.py" line={v.code.line} /></> : <span className="muted">—</span>}</td>
                  <td>{v.example ? <><code>{v.example.value || '""'}</code>{v.example.commented && <span className="muted small"> (בהערה)</span>}<br /><Loc file=".env.example" line={v.example.line} /></> : <span className="muted">—</span>}</td>
                  <td>{v.compose ? <><code>{v.compose.required ? "חובה" : (v.compose.default ?? "—") || '""'}</code><br /><Loc file="docker-compose.yml" line={v.compose.line} /></> : <span className="muted">לא מועבר</span>}</td>
                  <td>{v.prod ? <><code>{v.prod.required ? "חובה" : (v.prod.default ?? "—") || '""'}</code><br /><Loc file="prod/docker-compose.yml" line={v.prod.line} /></> : <span className="muted">—</span>}</td>
                  <td>{v.readers.length ? v.readers.map((r) => <div key={r.file}><Loc file={r.file} line={r.line} /></div>) : <span className="muted">—</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
