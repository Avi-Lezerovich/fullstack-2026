import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import "../styles/base.css";
import "../styles/content.css";
import "../styles/tools.css";
import "../styles/shell.css";
import "../styles/exam.css";
import ExamApp from "./ExamApp";
import { registerSW } from "../shared/offline";

createRoot(document.getElementById("root")!).render(
  <StrictMode><HashRouter><ExamApp /></HashRouter></StrictMode>,
);
registerSW();
