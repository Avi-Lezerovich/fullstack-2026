/* Commands, collapsible by group and by command. The copy button is always on the summary
   line, so a command can be copied without opening it. Pinned ones sit on top. */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Collapse from "../../shared/Collapse";
import { norm } from "../../shared/Palette";
import { persisted, useStore } from "../../shared/store";
import { copy } from "../../shared/toast";
import { GROUPS, SHELL_LABEL, type Cmd } from "../commands";
import { pinsStore } from "../work";

const openGroupsStore = persisted<string[]>("lolsuit-exam-cmd-open", ["run"]);
const keyOf = (g: string, c: Cmd) => g + "/" + c.title;

export default function Commands() {
  const [params] = useSearchParams();
  const [q, setQ] = useState("");
  const [showAll, setShowAll] = useState(false);
  const pins = useStore(pinsStore);
  const openGroups = useStore(openGroupsStore);
  const focus = params.get("open");
  useEffect(() => { if (focus) { openGroupsStore.set((o) => o.includes(focus) ? o : [...o, focus]); setTimeout(() => document.getElementById("cg-" + focus)?.scrollIntoView({ block: "start" }), 50); } }, [focus]);

  const toks = norm(q).split(" ").filter(Boolean);
  const match = (c: Cmd, gTitle: string) => { const h = norm(c.title + " " + c.cmd + " " + (c.note || "") + " " + (c.keys || "") + " " + gTitle); return toks.every((t) => h.includes(t)); };
  const groups = useMemo(() => GROUPS.map((g) => ({ ...g, items: g.items.filter((c) => match(c, g.title)) })).filter((g) => g.items.length), [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const pinned = GROUPS.flatMap((g) => g.items.filter((c) => pins.includes(keyOf(g.id, c))).map((c) => ({ g, c })));
  const searching = toks.length > 0;
  const total = groups.reduce((a, g) => a + g.items.length, 0);

  return (
    <div className="page">
      <div className="page-head">
        <h1>פקודות <small>Windows 11 · נתיב הפרויקט <code>C:\Users\lzr\Documents\GitHub\fullstack-2026</code></small></h1>
        <p>"העתק" מעתיק את כל הבלוק. לחיצה על שורה פותחת את הפקודה המלאה והסבר. ☆ מצמיד פקודה לראש הדף.</p>
      </div>
      <div className="filter-bar sticky">
        <input className="search big" type="search" autoFocus placeholder="סינון: pytest, logs, port, mysql, git restore, curl…" aria-label="סינון פקודות" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="count">{total} פקודות</span>
        <label className="chk-inline"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> להציג את כל הפקודות פתוחות</label>
        <button className="btn sm" type="button" onClick={() => openGroupsStore.set(openGroups.length ? [] : GROUPS.map((g) => g.id))}>{openGroups.length ? "כווץ קבוצות" : "פתח קבוצות"}</button>
      </div>

      {pinned.length > 0 && !searching && (
        <section className="cmd-group pinned">
          <h3>☆ מוצמדות</h3>
          {pinned.map(({ g, c }) => <CmdRow key={keyOf(g.id, c)} gid={g.id} c={c} open={showAll} />)}
        </section>
      )}

      {groups.map((g) => (
        <Collapse key={g.id} id={"cg-" + g.id} className="cmd-group" open={searching || openGroups.includes(g.id)}
          onToggle={(v) => { if (!searching) openGroupsStore.set((o) => v ? (o.includes(g.id) ? o : [...o, g.id]) : o.filter((x) => x !== g.id)); }}
          title={<><span className="cg-ic" aria-hidden="true">{g.icon}</span>{g.title}</>} meta={<span className="cg-n">{g.items.length}</span>}>
          {g.intro && <p className="cg-intro">{g.intro}</p>}
          {g.items.map((c) => <CmdRow key={keyOf(g.id, c)} gid={g.id} c={c} open={showAll || (searching && g.items.length <= 3)} />)}
        </Collapse>
      ))}
      {!groups.length && <p className="muted">אין פקודה כזו. בחיפוש המהיר (Ctrl+K) מחפשים גם בקוד ובתקלות.</p>}
    </div>
  );
}

function CmdRow({ gid, c, open }: { gid: string; c: Cmd; open: boolean }) {
  const pins = useStore(pinsStore);
  const k = keyOf(gid, c);
  const pinned = pins.includes(k);
  const lines = c.cmd.split("\n");
  return (
    <details className={"cmd" + (c.danger ? " danger" : "")} open={open || undefined}>
      <summary>
        <span className="clp-chev" aria-hidden="true" />
        <span className="cmd-title">{c.title}</span>
        <code className="cmd-peek">{lines[0]}{lines.length > 1 ? `  (+${lines.length - 1})` : ""}</code>
        <span className="cmd-meta" onClick={(e) => e.preventDefault()}>
          {c.shell && <span className={"shell s-" + c.shell}>{SHELL_LABEL[c.shell]}</span>}
          {c.danger && <span className="shell s-danger">זהירות</span>}
          <button type="button" className={"pin" + (pinned ? " on" : "")} aria-label={pinned ? "בטל הצמדה" : "הצמד"} title={pinned ? "בטל הצמדה" : "הצמד לראש הדף"}
            onClick={() => pinsStore.set((p) => pinned ? p.filter((x) => x !== k) : [...p, k])}>{pinned ? "★" : "☆"}</button>
          <button type="button" className="btn sm primary" onClick={() => copy(c.cmd, c.title)}>העתק</button>
        </span>
      </summary>
      <div className="cmd-body">
        <pre><code>{c.cmd}</code></pre>
        {c.note && <p className="cmd-note">{c.note}</p>}
        {lines.length > 1 && <div className="cmd-lines">{lines.map((l, i) => <button key={i} type="button" className="btn sm" onClick={() => copy(l)}>העתק שורה {i + 1}</button>)}</div>}
      </div>
    </details>
  );
}
