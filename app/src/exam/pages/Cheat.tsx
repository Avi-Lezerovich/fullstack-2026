import HtmlContent from "../../shared/HtmlContent";
import { cheatHtml } from "../../shared/content";

export default function Cheat() {
  return (
    <div className="page">
      <div className="page-head">
        <h1>דף הלילה האחרון <small>הכול בעמוד אחד</small></h1>
        <button className="btn sm" type="button" onClick={() => window.print()}>הדפסה</button>
      </div>
      <HtmlContent className="cheat-page" html={cheatHtml} />
    </div>
  );
}
