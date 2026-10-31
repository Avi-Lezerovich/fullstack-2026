/* The 25 change recipes, collapsible, filterable by level and text. */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import HtmlContent from "../../shared/HtmlContent";
import Collapse from "../../shared/Collapse";
import { cookbookIntroHtml, recipes, type Recipe } from "../../shared/content";
import { norm } from "../../shared/Palette";
import { reveal } from "../../shared/nav";
import { useStore } from "../../shared/store";
import { taskStore } from "../work";
import { OpenAllButton } from "../Refs";

const LEVELS: [Recipe["level"] | "all", string][] = [["all", "הכול"], ["easy", "קל"], ["med", "בינוני"], ["hard", "מתקדם"]];
const LABEL = { easy: "קל", med: "בינוני", hard: "מתקדם" };

export default function Recipes() {
  const [params] = useSearchParams();
  const open = params.get("open");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState<Recipe["level"] | "all">("all");
  const [openIds, setOpenIds] = useState<Set<string>>(new Set(open ? [open] : []));
  const task = useStore(taskStore);
  const navigate = useNavigate();
  useEffect(() => { if (open) { setOpenIds((s) => new Set(s).add(open)); reveal(open); } }, [open]);
  const toks = norm(q).split(" ").filter(Boolean);
  const list = useMemo(() => recipes.filter((r) => (level === "all" || r.level === level) && toks.every((t) => norm(r.title + " " + r.html.replace(/<[^>]+>/g, " ")).includes(t))), [q, level]); // eslint-disable-line react-hooks/exhaustive-deps
  const work = (r: Recipe) => { taskStore.set({ kind: "recipe", id: r.id, title: `${r.num}. ${r.title}`, refs: r.refs, verifyHtml: r.verifyHtml }); navigate("/work"); };
  const toggle = (id: string, v: boolean) => setOpenIds((s) => { const n = new Set(s); if (v) n.add(id); else n.delete(id); return n; });

  return (
    <div className="page">
      <div className="page-head">
        <h1>מתכוני שינוי <small>{recipes.length} שינויים שבוחן עלול לבקש</small></h1>
      </div>
      <HtmlContent html={cookbookIntroHtml} />
      <div className="filter-bar sticky">
        <input className="search big" type="search" placeholder="סינון: סיסמה, צבע, endpoint, עמודה, פורט…" aria-label="סינון מתכונים" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="seg">{LEVELS.map(([l, label]) => <button key={l} type="button" aria-pressed={level === l} onClick={() => setLevel(l)}>{label}</button>)}</div>
        <span className="count">{list.length} מתכונים</span>
        <button className="btn sm" type="button" onClick={() => setOpenIds(openIds.size ? new Set() : new Set(list.map((r) => r.id)))}>{openIds.size ? "סגור הכל" : "פתח הכל"}</button>
      </div>
      <div className="recipes">
        {list.map((r) => (
          <Collapse key={r.id} id={r.id} className={"recipe-c" + (task?.id === r.id ? " is-task" : "")} open={openIds.has(r.id)} onToggle={(v) => toggle(r.id, v)}
            title={<><span className={"tag " + r.level}>{LABEL[r.level]}</span><span className="rn">{r.num}</span><span dangerouslySetInnerHTML={{ __html: r.titleHtml }} /></>}
            meta={<>
              <OpenAllButton refs={r.refs} label="VS Code" />
              <button className="btn sm" type="button" onClick={() => work(r)}>{task?.id === r.id ? "✓ שלי" : "עובד על זה"}</button>
            </>}>
            {openIds.has(r.id) && <HtmlContent className="in" html={r.html} />}
          </Collapse>
        ))}
      </div>
    </div>
  );
}
