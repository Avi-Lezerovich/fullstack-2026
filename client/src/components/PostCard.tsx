import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";

import type { Post } from "../types";
import { formatRelative } from "../utils/dateUtils";
import { getInitials } from "../utils/stringUtils";

/** How many characters of the body to show before the "קרא עוד" (Read More) cut-off. */
const PREVIEW_LENGTH = 180;

interface PostCardProps {
  post: Post;
}

/**
 * The lawsuit card — the single Post display used in the Home feed and on profile pages.
 * Shows the author, title, the accused party, the charges as chips, and the body
 * (truncated with a "Read More" toggle). Read-only: no voting or delete.
 */
const PostCard = ({ post }: PostCardProps) => {
  const [expanded, setExpanded] = useState(false);

  const isLong = post.body.length > PREVIEW_LENGTH;
  const bodyText = expanded || !isLong ? post.body : `${post.body.slice(0, PREVIEW_LENGTH)}…`;

  return (
    <Card>
      <CardContent>
        {/* Author header */}
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
          <Avatar
            component={RouterLink}
            to={`/user-posts/${post.author_id}`}
            sx={{ bgcolor: "primary.main", color: "background.default", fontWeight: 700, textDecoration: "none" }}
          >
            {getInitials(post.author_name)}
          </Avatar>
          <Box>
            <Typography
              component={RouterLink}
              to={`/user-posts/${post.author_id}`}
              sx={{ fontWeight: 700, color: "primary.dark", textDecoration: "none" }}
            >
              {post.author_name}
            </Typography>
            <Typography variant="caption" sx={{ display: "block", color: "text.secondary" }}>
              {formatRelative(post.created_at)}
            </Typography>
          </Box>
        </Stack>

        {/* Title */}
        <Typography
          variant="h5"
          component="h2"
          sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, color: "primary.dark", mb: 1 }}
        >
          {post.title}
        </Typography>

        {/* Parties line */}
        <Typography sx={{ color: "text.secondary", mb: 1.5 }}>
          <GavelIcon sx={{ fontSize: 18, verticalAlign: "text-bottom", color: "secondary.main", ml: 0.5 }} />
          הנתבע: <strong>{post.defendant}</strong>
        </Typography>

        {/* Charges */}
        {post.charges && post.charges.length > 0 && (
          <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: "wrap", gap: 1 }}>
            {post.charges.map((charge) => (
              <Chip key={charge} label={charge} size="small" color="secondary" variant="outlined" />
            ))}
          </Stack>
        )}

        {/* Body + Read More */}
        <Typography sx={{ color: "text.primary", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
          {bodyText}
        </Typography>
        {isLong && (
          <Button size="small" onClick={() => setExpanded((v) => !v)} sx={{ mt: 0.5 }}>
            {expanded ? "הצג פחות" : "קרא עוד"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default PostCard;
