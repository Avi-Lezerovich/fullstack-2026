import { useState } from "react";

import { Box, Button } from "@mui/material";

import type { Post } from "../../types";
import { sanitizeHtml, htmlTextLength } from "../../utils/htmlUtils";

/** Plain-text length (chars) above which the body is collapsed behind "קרא עוד". */
const PREVIEW_LENGTH = 220;

/**
 * Renders the post body as sanitized rich-text HTML. Long bodies are clamped
 * with a CSS line-clamp and revealed by a "קרא עוד" (Read More) toggle.
 */
const PostBody = ({ post }: { post: Post }) => {
  const [expanded, setExpanded] = useState(false);
  const isLong = htmlTextLength(post.body) > PREVIEW_LENGTH;
  const html = sanitizeHtml(post.body);

  return (
    <>
      <Box
        dangerouslySetInnerHTML={{ __html: html }}
        sx={{
          color: "text.primary",
          lineHeight: 1.7,
          "& p": { m: 0, mb: 1 },
          "& p:last-child": { mb: 0 },
          "& a": { color: "secondary.main", textDecoration: "underline" },
          "& ul, & ol": { mr: 3, my: 1 },
          ...(!expanded && isLong
            ? {
                display: "-webkit-box",
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }
            : {}),
        }}
      />
      {isLong && (
        <Button size="small" onClick={() => setExpanded((v) => !v)} sx={{ mt: 0.5 }}>
          {expanded ? "הצג פחות" : "קרא עוד"}
        </Button>
      )}
    </>
  );
};

export default PostBody;
