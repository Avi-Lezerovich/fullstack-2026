/**
 * HTML sanitization for user-authored rich text (post bodies).
 * The WYSIWYG editor (TipTap) emits HTML; we store it as-is and sanitize at
 * render time so a malicious body can never inject script/handlers into the DOM.
 */
import DOMPurify from "dompurify";

// Only the formatting the editor can produce: bold, italics, links, lists, paragraphs.
const ALLOWED_TAGS = ["b", "strong", "i", "em", "u", "s", "a", "p", "br", "ul", "ol", "li"];
const ALLOWED_ATTR = ["href", "target", "rel"];

// Force every link to open safely in a new tab (no reverse-tabnabbing).
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer nofollow");
  }
});

/** Return a sanitized HTML string safe to pass to dangerouslySetInnerHTML. */
export const sanitizeHtml = (html: string): string =>
  DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });

/** Plain-text length of an HTML string — used to decide the "read more" cut-off. */
export const htmlTextLength = (html: string): number => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent || "").trim().length;
};
