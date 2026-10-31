/* Tool 2: every endpoint as a chain — the component that calls it, the api.ts function,
   the Flask route, the service functions, and the tables they touch. */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Collapse from "../../shared/Collapse";
import { norm } from "../../shared/Palette";
import { reveal } from "../../shared/nav";
import { openFile, openUsages } from "../../shared/pane";
import { useStore } from "../../shared/store";
import { openAllInVSCode, openInVSCode } from "../../shared/vscode";
import { mapsStore, type Chain, type Loc } from "../maps";

const short = (f: string) => f.split("/").pop();
const METHODS = ["ALL", "GET", "POST", "PATCH", "DELETE"];

export default function Flows() {
  const maps = useStore(mapsStore);
  const [params] = useSearchParams();
  const open = params.get("open");
  const [q, setQ] = useState("");
  const [method, setMethod] = useState("ALL");
  useEffect(() => { if (open) reveal("ch-" + open); }, [open, maps]);
  const toks = norm(q).split(" ").filter(Boolean);
  const list = useMemo(() => (maps?.chains || []).filter((c) => {
    if (method !== "ALL" && c.method !== method) return false;
    const h = norm([c.fn, c.method, c.path, c.route?.handler, c.route?.file, ...c.services.map((s) => s.name), ...c.tables.map((t) => t.name), ...c.callers.map((x) => x.file)].join(" "));
    return toks.every((t) => h.includes(t));
  }), [maps, q, method]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!maps) return <div className="page"><p className="muted">טוען זרימות…</p></div>;
  return (
    <div className="page">
      <div className="page-head">
        <h1>זרימות <small>כפתור → api.ts → route → service → טבלה</small></h1>
        <p>כל קריאת API של הקליינט, עם כל השכבות שהיא עוברת. שימושי כש"מוסיפים שדה" או "משנים התנהגות של כפתור": רואים בבת אחת את כל הקבצים. נבנה מהקוד ב־commit <code>{maps.commit}</code>.</p>
      </div>
      <div className="filter-bar sticky">
        <input className="search big" type="search" autoFocus placeholder="סינון: like, comments, users, likes_service, טבלה…" aria-label="סינון זרימות" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="seg">{METHODS.map((m) => <button key={m} type="button" aria-pressed={method === m} onClick={() => setMethod(m)}>{m === "ALL" ? "הכול" : m}</button>)}</div>
        <span className="count">{list.length} endpoints</span>
      </div>
      <div className="flows">
        {list.map((c) => <ChainRow key={c.fn} c={c} open={open === c.fn || (toks.length > 0 && list.length <= 3)} />)}
      </div>
      {maps.orphans.length > 0 && (
        <section className="panel" style={{ marginTop: 24 }}>
          <div className="panel-head"><b>Routes בלי קריאה מ־api.ts</b><span className="muted">SSE, קבצים, או curl בלבד</span></div>
          <ul className="orphans">
            {maps.orphans.map((o) => (
              <li key={o.method + o.path}>
                <span className={"m m-" + o.method}>{o.method}</span><code>{o.path}</code>
                <Node label={`${short(o.file)} · ${o.handler}()`} loc={{ file: o.file, line: o.handlerLine }} />
                {o.services.map((s) => <Node key={s.name} label={s.name} loc={s} />)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Node({ label, loc, kind, sym }: { label: string; loc: Loc; kind?: string; sym?: string }) {
  return (
    <span className={"node" + (kind ? " k-" + kind : "")}>
      <button type="button" className="node-main" title={`${loc.file}:${loc.line}`} onClick={() => openFile(loc.file, loc.line)}>{label}</button>
      <button type="button" className="node-vs" title="פתח ב־VS Code" onClick={() => openInVSCode(loc.file, loc.line)}>VS</button>
      {sym && <button type="button" className="node-vs" title="איפה עוד משתמשים בזה" onClick={() => openUsages(sym)}>⌕</button>}
    </span>
  );
}

function ChainRow({ c, open }: { c: Chain; open: boolean }) {
  const all: Loc[] = [...c.callers, c.client, ...(c.route ? [{ file: c.route.file, line: c.route.handlerLine }] : []), ...c.services, ...c.tables];
  return (
    <Collapse id={"ch-" + c.fn} className="chain" open={open}
      title={<><span className={"m m-" + c.method}>{c.method}</span><code className="ch-path">{c.path}</code><span className="ch-fn">{c.fn}()</span>
        {c.route?.auth && <span className={"auth a-" + c.route.auth}>{c.route.auth.replace("_", " ")}</span>}
        {c.tables.length > 0 && <span className="ch-tables">{c.tables.map((t) => t.name).join(" · ")}</span>}</>}
      meta={<button type="button" className="btn sm" title="פותח את כל הקבצים בשרשרת" onClick={() => openAllInVSCode(perFileLocs(all))}>VS Code ×{perFileLocs(all).length}</button>}>
      <div className="chain-flow">
        <div className="layer l-client">
          <span className="layer-t">רכיב</span>
          {c.callers.length ? c.callers.map((x) => <Node key={x.file} label={short(x.file)!} loc={x} kind="client" />) : <span className="muted">אין קורא ב־client/src</span>}
        </div>
        <span className="arrow">←</span>
        <div className="layer l-client"><span className="layer-t">api.ts</span><Node label={c.fn + "()"} loc={c.client} kind="client" sym={c.fn} /></div>
        <span className="arrow">←</span>
        <div className="layer l-api">
          <span className="layer-t">route</span>
          {c.route ? <Node label={`${short(c.route.file)} · ${c.route.handler}()`} loc={{ file: c.route.file, line: c.route.handlerLine }} kind="api" sym={c.route.handler} /> : <span className="muted">לא נמצא</span>}
        </div>
        <span className="arrow">←</span>
        <div className="layer l-svc">
          <span className="layer-t">service</span>
          {c.services.length ? c.services.map((s) => <Node key={s.name} label={s.name + "()"} loc={s} kind="svc" sym={s.name.split(".")[1]} />) : <span className="muted">בלי service (ישירות ב־route)</span>}
        </div>
        <span className="arrow">←</span>
        <div className="layer l-db">
          <span className="layer-t">טבלאות</span>
          {c.tables.length ? c.tables.map((t) => <Node key={t.name} label={t.name} loc={t} kind="db" sym={t.name} />) : <span className="muted">—</span>}
        </div>
      </div>
      {c.route && <p className="chain-note">ה־route: <code>{c.method} {c.route.path}</code>{c.route.auth ? <> · הרשאה: <code>@security.{c.route.auth}</code></> : " · בלי decorator הרשאה"}. טבלאות לפי ה־SQL בפונקציות ה־service ובעזרים הפרטיים שלהן.</p>}
    </Collapse>
  );
}

function perFileLocs(locs: Loc[]) {
  const m = new Map<string, { path: string; line: number }>();
  locs.forEach((l) => { if (!m.has(l.file)) m.set(l.file, { path: l.file, line: l.line }); });
  return [...m.values()];
}
