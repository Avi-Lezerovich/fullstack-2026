import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import "../styles/base.css";
import "../styles/content.css";
import "../styles/tools.css";
import "../styles/shell.css";
import StudyApp from "./StudyApp";
import { registerSW } from "../shared/offline";

// old links were #t5; the router wants #/t/t5
if (/^#t\d+$/.test(location.hash)) history.replaceState(null, "", "#/t/" + location.hash.slice(1));

createRoot(document.getElementById("root")!).render(
  <StrictMode><HashRouter><StudyApp /></HashRouter></StrictMode>,
);
registerSW();
