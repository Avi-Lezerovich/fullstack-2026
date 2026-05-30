import { useState } from "react";

import {
  Button,
  Typography,
} from "@mui/material";


import type { Post } from "../../types";


/** How many characters of the body to show before the "קרא עוד" (Read More) cut-off. */
const PREVIEW_LENGTH = 160;



const PostBody = ({ post }: { post: Post }) => {
  const [expanded, setExpanded] = useState(false);

  const isLong = post.body.length > PREVIEW_LENGTH;
  const bodyText = expanded || !isLong ? post.body : `${post.body.slice(0, PREVIEW_LENGTH)}…`;
    return (
        <>
        {/* Body + Read More */}
        <Typography sx={{ color: "text.primary", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
          {bodyText}
        </Typography>
        {isLong && (
          <Button size="small" onClick={() => setExpanded((v) => !v)} sx={{ mt: 0.5 }}>
            {expanded ? "הצג פחות" : "קרא עוד"}
          </Button>
        )}
        </>
    );
};

export default PostBody;