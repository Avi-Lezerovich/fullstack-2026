/* The exam window: tools for while the exam is running. Topics belong to the study window
   (index.html); links to them open there. */
import { useEffect, useMemo, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import Shell, { useBoot } from "../shared/Shell";
import CodePane from "../shared/CodePane";
import Palette, { paneShortcuts, type PalItem } from "../shared/Palette";
import { setNavigator, openStudy } from "../shared/nav";
import { openFile } from "../shared/pane";
import { finderGroups, recipes, troubleRows } from "../shared/content";
import { useStore } from "../shared/store";
import { copy } from "../shared/toast";
import { openInVSCode } from "../shared/vscode";
import { GROUPS } from "./commands";
import { loadMaps, mapsStore } from "./maps";
import Timer from "./Timer";
import Dashboard from "./pages/Dashboard";
import Finder from "./pages/Finder";
import Recipes from "./pages/Recipes";
import Commands from "./pages/Commands";
import Trouble from "./pages/Trouble";
import Cheat from "./pages/Cheat";
import CodePage from "./pages/CodePage";
import Flows from "./pages/Flows";
import EnvMap from "./pages/EnvMap";
import Workbench from "./pages/Workbench";

/* topic → page in this window; anything else opens in the study window */
const ROUTE_OF: Record<string, string> = { t0: "/finder", t13: "/recipes", t16: "/cheat", t17: "/commands", t19: "/trouble" };

export const NAV: [path: string, label: string, icon: string][] = [
  ["/", "לוח", "◧"],
  ["/finder", "איפה זה?", "⌖"],
  ["/recipes", "מתכונים", "☰"],
  ["/work", "שולחן עבודה", "✎"],
  ["/commands", "פקודות", "›_"],
  ["/code", "קוד", "</>"],
  ["/flows", "זרימות", "⇄"],
  ["/env", "משתנים ופורטים", "⚙"],
  ["/trouble", "תקלות", "⚠"],
  ["/cheat", "דף לילה", "★"],
];

export default function ExamApp() {
  useBoot();
  useEffect(() => { loadMaps(); }, []);
  const navigate = useNavigate();
  const loc = useLocation();
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [loc.pathname]);
  useEffect(() => setNavigator(({ topic, at }) => {
    if (at && /^fx-/.test(at)) { navigate("/finder?open=" + at); return; }
    if (at && /^r\d+$/.test(at)) { navigate("/recipes?open=" + at); return; }
    if (ROUTE_OF[topic]) { navigate(ROUTE_OF[topic]); return; }
    openStudy(`/t/${topic}` + (at ? `?at=${at}` : ""));
  }), [navigate]);

  const maps = useStore(mapsStore);
  const extra = useMemo<PalItem[]>(() => {
    const items: PalItem[] = [];
    GROUPS.forEach((g) => g.items.forEach((c) => items.push({
      type: "cmd", title: c.title, sub: g.title + " · " + c.cmd.split("\n")[0], keys: c.cmd + " " + (c.keys || "") + " " + (c.note || ""),
      run: () => { copy(c.cmd, "הפקודה"); navigate("/commands?open=" + g.id); },
    })));
    troubleRows.forEach((r) => items.push({ type: "trouble", title: r.symptom, sub: r.section, keys: r.causeHtml.replace(/<[^>]+>/g, "") + " " + r.fixHtml.replace(/<[^>]+>/g, ""), run: () => navigate("/trouble?open=" + r.id) }));
    maps?.chains.forEach((c) => items.push({
      type: "flow", title: `${c.method} ${c.path}`, sub: `${c.fn} → ${c.route?.handler || "?"} → ${c.services.map((s) => s.name).join(", ") || "—"}`, keys: c.tables.map((t) => t.name).join(" "),
      run: () => navigate("/flows?open=" + c.fn),
    }));
    maps?.env.forEach((v) => items.push({
      type: "env", title: v.name, sub: v.code ? `config.py:${v.code.line} · ברירת מחדל ${v.code.default || '""'}` : "לא נקרא ב־config.py",
      run: (alt) => v.code ? (alt ? openInVSCode("server/app/config.py", v.code.line) : openFile("server/app/config.py", v.code.line)) : navigate("/env?q=" + v.name),
    }));
    return items;
  }, [maps, navigate]);

  const shortcuts: PalItem[] = useMemo(() => [
    { type: "go", title: "איפה זה? ביקשו לשנות X", sub: `${finderGroups.reduce((a, g) => a + g.items.length, 0)} רשומות עם קובץ ושורה`, run: () => navigate("/finder") },
    { type: "go", title: "מתכוני שינוי", sub: `${recipes.length} מתכונים צעד אחר צעד`, run: () => navigate("/recipes") },
    { type: "go", title: "שולחן עבודה", sub: "בודק diff, צ'קליסט ופקודות git", run: () => navigate("/work") },
    { type: "go", title: "פקודות", sub: "הרצה, דוקר, טסטים, git, curl, MySQL", run: () => navigate("/commands") },
    ...paneShortcuts(),
  ], [navigate]);

  const onCode = loc.pathname === "/code";
  return (
    <Shell kind="exam" sub="חלון מבחן · כלי עבודה"
      nav={<button className="iconbtn menu-btn" type="button" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>☰ כלים</button>}
      right={<button className="iconbtn switch-btn" type="button" onClick={() => openStudy()} title="פותח את חלון הלימוד בחלון/לשונית נפרדים">📖 <span className="lbl">חלון לימוד</span> ↗</button>}>
      <nav className={"exam-nav" + (menu ? " open" : "")} aria-label="כלים">
        {NAV.map(([path, label, icon]) => (
          <NavLink key={path} to={path} end={path === "/"} className={({ isActive }) => "en-link" + (isActive ? " active" : "")}>
            <span className="en-ic" aria-hidden="true">{icon}</span>{label}
          </NavLink>
        ))}
      </nav>
      <main className={"exam-main" + (onCode ? " is-code" : "")}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/finder" element={<Finder />} />
          <Route path="/recipes" element={<Recipes />} />
          <Route path="/work" element={<Workbench />} />
          <Route path="/commands" element={<Commands />} />
          <Route path="/code" element={<CodePage />} />
          <Route path="/flows" element={<Flows />} />
          <Route path="/env" element={<EnvMap />} />
          <Route path="/trouble" element={<Trouble />} />
          <Route path="/cheat" element={<Cheat />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
      </main>
      {!onCode && <CodePane />}
      <Palette extra={extra} shortcuts={shortcuts} />
      <Timer />
    </Shell>
  );
}
