/* The study window: topics one at a time, progress as a trial's phases, Q&A drills and
   timed practice. Exam-time tools live in the other window (exam.html). */
import { useEffect, useMemo, useState } from "react";
import { Link, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Shell, { useBoot } from "../shared/Shell";
import CodePane from "../shared/CodePane";
import Palette, { paneShortcuts, type PalItem } from "../shared/Palette";
import HtmlContent from "../shared/HtmlContent";
import { topics, topicById, type Topic } from "../shared/content";
import { setNavigator, openExam, reveal } from "../shared/nav";
import { persisted, useStore } from "../shared/store";
import { offlineStore } from "../shared/offline";
import { labelBackgrounds } from "../shared/diagrams";
import Practice from "./Practice";

/* topics the exam window shows as its own pages */
const EXAM_ROUTE: Record<string, string> = { t0: "/finder" };

interface StudyState { done: Record<string, boolean>; current?: string }
export const studyStore = persisted<StudyState>("lolsuit-study-v2", { done: {} });

const PHASES = ["הוגשה", "איסוף עדויות", "דיוני מושבעים", "ניתן פסק דין", "התיק נסגר"];
const studied = topics.filter((t) => t.studied);
const order = topics.filter((t) => !EXAM_ROUTE[t.id]);
function phaseIndex(n: number, total: number) { return n >= total ? 4 : Math.min(3, Math.floor(n / (total / 4))); }
const plain = (html: string) => html.replace(/<[^>]+>/g, "");

export default function StudyApp() {
  useBoot();
  const navigate = useNavigate();
  useEffect(() => setNavigator(({ topic, at }) => {
    if (EXAM_ROUTE[topic]) { openExam(EXAM_ROUTE[topic] + (at ? "?open=" + at : "")); return; }
    navigate(`/t/${topic}` + (at ? `?at=${at}` : ""));
  }), [navigate]);
  const st = useStore(studyStore);
  const n = studied.filter((t) => st.done[t.id]).length;
  const p = phaseIndex(n, studied.length);
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => setMenu(false), [loc.pathname]);

  const shortcuts: PalItem[] = useMemo(() => [
    { type: "go", title: "חלון מבחן: איפה זה?", sub: "ביקשו לשנות X — קובץ ושורה", run: () => openExam("/finder") },
    { type: "go", title: "תרגול תחת שעון", sub: "משימה אקראית, טיימר ופתרון מוסתר", run: () => navigate("/t/t20") },
    { type: "go", title: "שאלות מבחן", sub: "תשובות מודל", run: () => navigate("/t/t14") },
    ...paneShortcuts(),
  ], [navigate]);

  return (
    <Shell kind="study" sub="חלון לימוד · Full Stack RUNI 2026"
      nav={<button className="iconbtn menu-btn" type="button" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>☰ נושאים</button>}
      right={<>
        <div className="status" title="התקדמות הלימוד">
          <span className="chip">{PHASES[p]} · {n}/{studied.length}</span>
          <span className="meter" aria-hidden="true"><i style={{ width: (100 * n / studied.length) + "%" }} /></span>
        </div>
        <button className="iconbtn switch-btn" type="button" onClick={() => openExam()} title="פותח את חלון המבחן בחלון/לשונית נפרדים">⏱ <span className="lbl">חלון מבחן</span> ↗</button>
      </>}>
      <div className={"layout" + (menu ? " menu-open" : "")}>
        <Sidebar />
        <main id="main"><div className="wrap">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/t/:id" element={<TopicView />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </div></main>
      </div>
      <CodePane />
      <Palette shortcuts={shortcuts} />
    </Shell>
  );
}

/* ---------- sidebar ---------- */
function Sidebar() {
  const st = useStore(studyStore);
  const off = useStore(offlineStore);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const hits = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return null;
    const out: Record<string, number> = {};
    for (const t of order) {
      const text = plain(t.html + " " + t.heading).toLowerCase();
      let k = 0, i = text.indexOf(s);
      while (i >= 0) { k++; i = text.indexOf(s, i + s.length); }
      if (k) out[t.id] = k;
    }
    return out;
  }, [q]);
  const total = hits ? Object.values(hits).reduce((a, b) => a + b, 0) : 0;
  return (
    <nav className="side" aria-label="תוכן העניינים">
      <button className="btn primary quick" type="button" onClick={() => window.dispatchEvent(new CustomEvent("open-palette"))}><span>⌕ חיפוש מהיר</span><kbd>Ctrl K</kbd></button>
      <h2>אינדקס התיק</h2>
      <input className="search" type="search" placeholder="סינון הנושאים, למשל dedupe_key" aria-label="חיפוש במדריך" value={q}
        onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setQ(""); }} />
      <div className="search-info" aria-live="polite">{hits ? (total ? `${total} התאמות ב־${Object.keys(hits).length} נושאים` : "אין תוצאות. נסו מונח באנגלית") : ""}</div>
      <ol className="toc">
        <li><Link className={pathname === "/" ? "active" : ""} to="/"><span className="num">⌂</span><span>פתיחה והתקדמות</span><span /></Link></li>
        {order.filter((t) => !hits || hits[t.id]).map((t) => (
          <li key={t.id} className={st.done[t.id] ? "done" : ""}>
            <a className={pathname === "/t/" + t.id ? "active" : ""} href={"#/t/" + t.id}
              onClick={(e) => { e.preventDefault(); navigate(`/t/${t.id}` + (q.trim() ? "?q=" + encodeURIComponent(q.trim()) : "")); }}>
              <span className="num">{String(t.num).padStart(2, "0")}</span><span>{t.title}</span>
              {hits ? <span className="hitn">{hits[t.id]}</span> : <span className="chk" aria-hidden="true">✔</span>}
            </a>
          </li>
        ))}
      </ol>
      <div className="side-card">
        <b>חלון המבחן</b>
        <p>איפה זה בקוד, מתכונים, פקודות, זרימות, משתנים ושעון. פותחים אותו בחלון נפרד ליד VS Code.</p>
        <button className="btn primary" type="button" onClick={() => openExam()}>פתח חלון מבחן ↗</button>
      </div>
      <p className="hint"><kbd>Ctrl</kbd>+<kbd>K</kbd> חיפוש מהיר · <kbd>←</kbd> הבא · <kbd>→</kbd> הקודם. כל <code>נתיב ↗</code> נפתח בקוד, ו־Alt+לחיצה פותחת ב־VS Code. ההתקדמות נשמרת בדפדפן הזה.</p>
      <p className={"offline-state" + (off.ready ? " ok" : "")}>{off.ready ? "✓ עובד גם בלי אינטרנט" : off.online ? "מכין עבודה בלי אינטרנט…" : "אין חיבור לרשת"}</p>
    </nav>
  );
}

/* ---------- home ---------- */
function Home() {
  const st = useStore(studyStore);
  const navigate = useNavigate();
  const n = studied.filter((t) => st.done[t.id]).length;
  const p = phaseIndex(n, studied.length);
  const next = order.find((t) => t.studied && !st.done[t.id]);
  const resume = st.current ? topicById(st.current) : undefined;
  return (
    <>
      <header className="filing">
        <div className="docket"><span>תיק לימוד · RUNI Full Stack 2026</span><span>חלון לימוד</span></div>
        <h1>LolSuit<em> בית המשפט לתביעות מצחיקות</em> — הכנה למבחן</h1>
        <p>איך המערכת בנויה, איך הנתונים זורמים בה, ואיך לבצע שינוי קטן בביטחון מול הבוחן. כל נתיב, פונקציה, פורט ופקודה נבדקו מול הקוד.</p>
        <p>מסמנים "נלמד" בכל נושא, והתיק עובר משלב לשלב עד פסק הדין. בזמן המבחן עצמו עובדים מ<b>חלון המבחן</b>.</p>
        <div className="phases">
          {PHASES.map((ph, i) => <span key={ph} className={"chip" + (i === p ? " on" : i < p ? " past" : "")}>{ph}</span>)}
        </div>
        <div className="big-actions">
          {resume && <button className="btn primary" type="button" onClick={() => navigate("/t/" + resume.id)}>המשך מאיפה שעצרת: {resume.num}. {resume.title}</button>}
          {next && next.id !== resume?.id && <button className="btn" type="button" onClick={() => navigate("/t/" + next.id)}>הנושא הבא שלא נלמד: {next.num}. {next.title}</button>}
          <button className="btn" type="button" onClick={() => navigate("/t/t20")}>⏱ תרגול תחת שעון</button>
          <button className="btn" type="button" onClick={() => openExam()}>חלון מבחן ↗</button>
        </div>
      </header>
      <div className="topic-grid">
        {order.map((t) => (
          <Link key={t.id} to={"/t/" + t.id} className={"topic-card" + (st.done[t.id] ? " done" : "")}>
            <span className="tc-n">{t.num}</span>
            <span className="tc-t">{t.title}</span>
            <span className="tc-s">{st.done[t.id] ? "✔ נלמד" : t.studied ? "לא נלמד עדיין" : ""}</span>
          </Link>
        ))}
      </div>
    </>
  );
}

/* ---------- one topic ---------- */
function TopicView() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const st = useStore(studyStore);
  const t = topicById(id);
  const i = order.findIndex((x) => x.id === id);
  const at = params.get("at"), q = params.get("q");

  useEffect(() => { if (t) { studyStore.set((s) => ({ ...s, current: t.id })); if (!at) window.scrollTo({ top: 0 }); } }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (/INPUT|TEXTAREA|SELECT/.test((document.activeElement || document.body).nodeName) || document.querySelector("dialog[open]")) return;
      // right-to-left page: the left arrow moves forward
      if (e.key === "ArrowLeft" && i < order.length - 1) { e.preventDefault(); navigate("/t/" + order[i + 1].id); }
      if (e.key === "ArrowRight" && i > 0) { e.preventDefault(); navigate("/t/" + order[i - 1].id); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [i, navigate]);

  if (!t) return <p>אין נושא כזה. <Link to="/">לדף הפתיחה</Link></p>;
  const setDone = (v: boolean) => studyStore.set((s) => ({ ...s, done: { ...s.done, [t.id]: v } }));
  const prev = order[i - 1], next = order[i + 1];

  return (
    <section className="topic" id={t.id}>
      <div className="topic-head">
        <div className="n">{t.num}</div>
        <h2 dangerouslySetInnerHTML={{ __html: t.heading }} />
        <span className="topic-pos">{t.studied ? `נושא ${t.num} מתוך ${studied.length}` : "כלי עבודה"}</span>
        {t.studied && <label className="done-toggle"><input type="checkbox" checked={!!st.done[t.id]} onChange={(e) => setDone(e.target.checked)} /> נלמד</label>}
        <button className="btn sm" type="button" title="פתח את כל תתי־הסעיפים" onClick={() => document.querySelectorAll<HTMLDetailsElement>("#main details.sub").forEach((d) => { d.open = true; })}>פתח הכל</button>
      </div>
      <TopicBody key={t.id} topic={t} at={at} q={q} />
      <nav className="pager" aria-label="מעבר בין נושאים">
        {prev ? <Link className="prev" to={"/t/" + prev.id}><span className="dir">→ הקודם</span><span className="ttl">{prev.num}. {prev.title}</span></Link> : <span className="empty" />}
        {next ? <Link className="next cta" to={"/t/" + next.id}><span className="dir">הבא ←</span><span className="ttl">{next.num}. {next.title}</span></Link> : <span className="empty" />}
        {t.studied && <button className="btn done-next" type="button" onClick={() => { setDone(true); if (next) navigate("/t/" + next.id); }}>
          {next ? "סמן כנלמד ועבור לנושא הבא" : "סמן כנלמד"}</button>}
      </nav>
    </section>
  );
}

function TopicBody({ topic, at, q }: { topic: Topic; at: string | null; q: string | null }) {
  return (
    <HtmlContent className="topic-body" html={topic.html} widgets={{ practice: <Practice /> }}
      onReady={(root) => {
        wireDrills(root);
        if (q) highlight(root, q.toLowerCase());
        if (at) reveal(at);
        labelBackgrounds(root);
      }} />
  );
}

/* the "random question / random recipe / open all" buttons inside topics 13 and 14 */
function wireDrills(root: HTMLElement) {
  const pickOne = (sel: string) => {
    const items = Array.from(root.querySelectorAll<HTMLDetailsElement>(sel));
    items.forEach((d) => { d.open = false; d.classList.remove("flash"); });
    const pick = items[Math.floor(Math.random() * items.length)];
    if (pick) reveal(pick.id);
  };
  const on = (id: string, fn: (b: HTMLElement) => void) => {
    const b = root.querySelector<HTMLElement>("#" + id);
    if (b && !b.dataset.wired) { b.dataset.wired = "1"; b.addEventListener("click", () => fn(b)); }
  };
  on("drillRecipe", () => pickOne("details.recipe"));
  on("drillQa", () => pickOne("details.qa"));
  on("qaOpenAll", (b) => {
    const qs = Array.from(root.querySelectorAll<HTMLDetailsElement>("details.qa"));
    const anyClosed = qs.some((d) => !d.open);
    qs.forEach((d) => { d.open = anyClosed; });
    b.textContent = anyClosed ? "הסתר את כל התשובות" : "חשוף את כל התשובות";
  });
}

/* mark every occurrence of q (port of core.js highlight) and open the details holding it */
function highlight(root: HTMLElement, q: string) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue || !node.nodeValue.toLowerCase().includes(q)) return NodeFilter.FILTER_REJECT;
      for (let p = node.parentNode; p && p !== root; p = p.parentNode) {
        if ((p as Element).namespaceURI === "http://www.w3.org/2000/svg" || p.nodeName === "BUTTON" || p.nodeName === "SCRIPT") return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes: Text[] = [];
  let node: Node | null;
  while ((node = walker.nextNode())) nodes.push(node as Text);
  let first: HTMLElement | null = null;
  nodes.forEach((n) => {
    const text = n.nodeValue!, lower = text.toLowerCase(), frag = document.createDocumentFragment();
    let i = 0, j: number;
    while ((j = lower.indexOf(q, i)) >= 0) {
      frag.appendChild(document.createTextNode(text.slice(i, j)));
      const m = document.createElement("mark");
      m.className = "hl"; m.textContent = text.slice(j, j + q.length);
      frag.appendChild(m);
      if (!first) first = m;
      i = j + q.length;
    }
    frag.appendChild(document.createTextNode(text.slice(i)));
    n.parentNode!.replaceChild(frag, n);
  });
  root.querySelectorAll<HTMLDetailsElement>("details").forEach((d) => { if (d.querySelector("mark.hl")) d.open = true; });
  if (first) setTimeout(() => (first as HTMLElement).scrollIntoView({ block: "center" }), 60);
}
