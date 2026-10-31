/* "Asked to change X — where is it?": the finder items as cards, each with its files
   (open all in VS Code) and a button to make it the current task. */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import HtmlContent from "../../shared/HtmlContent";
import { finderGroups, type FinderItem } from "../../shared/content";
import { norm } from "../../shared/Palette";
import { reveal } from "../../shared/nav";
import { useStore } from "../../shared/store";
import { taskStore } from "../work";
import { OpenAllButton } from "../Refs";

export default function Finder() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const open = params.get("open");
  const navigate = useNavigate();
  const task = useStore(taskStore);
  const toks = norm(q).split(" ").filter(Boolean);
  const groups = useMemo(() => finderGroups.map((g) => ({ ...g, items: g.items.filter((it) => { const h = norm(it.keys); return toks.every((t) => h.includes(t)); }) })).filter((g) => g.items.length), [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const count = groups.reduce((a, g) => a + g.items.length, 0);
  useEffect(() => { if (open) { setQ(""); reveal(open); } }, [open]);
  const work = (it: FinderItem) => { taskStore.set({ kind: "finder", id: it.id, title: it.q, refs: it.refs }); navigate("/work"); };

  return (
    <div className="page">
      <div className="page-head">
        <h1>איפה זה? <small>ביקשו לשנות X</small></h1>
        <p>מוצאים את מה שביקשו, ומקבלים קובץ ושורה, את המקומות שבהם אותו ערך משוכפל ("עדכן גם"), ואיך לוודא שזה עבד. <b>לחיצה</b> על נתיב פותחת אותו כאן, <b>Alt+לחיצה</b> פותחת ב־VS Code.</p>
      </div>
      <div className="filter-bar sticky">
        <input className="search big" type="search" autoFocus placeholder="סינון: צבע, סיסמה, פורט, לייק, מושבעים, endpoint…" aria-label="סינון רשומות"
          value={q} onChange={(e) => { setQ(e.target.value); if (open) setParams({}); }} />
        <span className="count">{toks.length ? `${count} רשומות` : `${count} רשומות ב־${groups.length} קבוצות`}</span>
        <div className="chips">
          {finderGroups.map((g) => <button key={g.title} type="button" className="chip-btn" onClick={() => document.getElementById("g-" + g.title)?.scrollIntoView({ block: "start" })}>{g.title}</button>)}
        </div>
      </div>
      {groups.map((g) => (
        <section key={g.title} className="fx-group" id={"g-" + g.title}>
          <h3>{g.title} <span className="lyr">{g.layer}</span></h3>
          <div className="fx-list">
            {g.items.map((it) => (
              <article key={it.id} className={"fx" + (task?.id === it.id ? " is-task" : "")} id={it.id}>
                <div className="fx-q">{it.q}</div>
                <HtmlContent html={it.html} />
                <div className="fx-actions">
                  <OpenAllButton refs={it.refs} label={it.refs.length > 1 ? undefined : "פתח ב־VS Code"} />
                  <button className="btn sm" type="button" onClick={() => work(it)}>{task?.id === it.id ? "✓ המשימה שלי" : "עובד על זה"}</button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
      {!groups.length && <p className="muted">אין התאמה. נסו את החיפוש המהיר (Ctrl+K), שמחפש גם בקוד עצמו.</p>}
    </div>
  );
}
