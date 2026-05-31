import { useState, useRef, useLayoutEffect } from "react";

import { Box, Button } from "@mui/material";

import type { Post } from "../../types";
import { sanitizeHtml } from "../../utils/htmlUtils";

/** How many lines of the body to show before collapsing behind "קרא עוד". */
const PREVIEW_LINES = 4;

/**
 * Renders the post body as sanitized rich-text HTML. Long bodies are clamped to
 * PREVIEW_LINES and revealed by a "קרא עוד" (Read More) toggle.
 *
 * The toggle is shown only when the body actually overflows the clamp — we measure
 * the rendered element (scrollHeight vs clientHeight) rather than guessing from the
 * text length, so the decision always matches what the user sees regardless of
 * formatting (paragraphs, line breaks) or viewport width.
 */
const PostBody = ({ post }: { post: Post }) => {
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const html = sanitizeHtml(post.body);

  // Measure the clamped element after layout, and re-measure on resize (a width
  // change reflows the text and changes how many lines it takes).
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const measure = () => {
      // Only meaningful while collapsed: that's when the clamp is applied.
      if (!expanded) setOverflowing(el.scrollHeight > el.clientHeight + 1);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [html, expanded]);

  return (
    <>
      <Box
        ref={bodyRef}
        dangerouslySetInnerHTML={{ __html: html }}
        sx={{
          color: "text.primary",
          lineHeight: 1.7,
          "& p": { m: 0, mb: 1 },
          "& p:last-child": { mb: 0 },
          "& a": { color: "secondary.main", textDecoration: "underline" },
          "& ul, & ol": { mr: 3, my: 1 },
          ...(!expanded
            ? {
                display: "-webkit-box",
                WebkitLineClamp: PREVIEW_LINES,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }
            : {}),
        }}
      />
      {(overflowing || expanded) && (
        <Button size="small" onClick={() => setExpanded((v) => !v)} sx={{ mt: 0.5 }}>
          {expanded ? "הצג פחות" : "קרא עוד"}
        </Button>
      )}
    </>
  );
};

export default PostBody;
