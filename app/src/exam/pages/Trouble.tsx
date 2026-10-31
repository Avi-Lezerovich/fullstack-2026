/* Troubleshooting: symptom first, cause and fix behind a click. */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import HtmlContent from "../../shared/HtmlContent";
import Collapse from "../../shared/Collapse";
import { troubleExtrasHtml, troubleRows } from "../../shared/content";
import { norm } from "../../shared/Palette";
import { reveal } from "../../shared/nav";
import Status from "../Status";

const strip = (h: string) => h.replace(/<[^>]+>/g, " ");

export default function Trouble() {
  const [params] = useSearchParams();
  const open = params.get("open");
  const [q, setQ] = useState("");
  useEffect(() => { if (open) reveal(open); }, [open]);
  const toks = norm(q).split(" ").filter(Boolean);
  const rows = useMemo(() => troubleRows.filter((r) => { const h = norm(r.symptom + " " + strip(r.causeHtml) + " " + strip(r.fixHtml) + " " + r.section); return toks.every((t) => h.includes(t)); }), [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const sections = [...new Set(rows.map((r) => r.section))];
  return (
    <div className="page">
      <div className="page-head">
        <h1>תקלות נפוצות <small>סימפטום → סיבה → פתרון</small></h1>
        <p>רוב הזמן שהולך לאיבוד במבחן הוא על "למה אני לא רואה את השינוי". קודם מחפשים כאן את הסימפטום, ורק אחר כך מנחשים.</p>
      </div>
      <div className="trouble-top">
        <Status compact />
        <HtmlContent html={troubleExtrasHtml} />
      </div>
      <div className="filter-bar sticky">
        <input className="search big" type="search" autoFocus placeholder="מה רואים? port, Access denied, 500, skipped, לא מופיע…" aria-label="סינון תקלות" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="count">{rows.length} תקלות</span>
      </div>
      {sections.map((s) => (
        <section key={s} className="ts-section">
          <h3>{s}</h3>
          {rows.filter((r) => r.section === s).map((r) => (
            <Collapse key={r.id} id={r.id} className="ts-c" open={!!(toks.length && rows.length <= 4) || open === r.id}
              title={<span dangerouslySetInnerHTML={{ __html: r.symptomHtml }} />}>
              <div className="ts-grid">
                <div><span className="lb">סיבה</span><HtmlContent html={r.causeHtml} /></div>
                <div><span className="lb ok">פתרון</span><HtmlContent html={r.fixHtml} /></div>
              </div>
            </Collapse>
          ))}
        </section>
      ))}
    </div>
  );
}
