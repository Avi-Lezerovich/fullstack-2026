
import {
  Box,
  Card,
  CardContent,
  CardMedia,
  Divider,
} from "@mui/material";

import type { Post } from "../../types";

import AuthorHeader from "./AuthorHeader";
import PostTitle from "./PostTitle";
import PostBody from "./PostBody";

interface PostCardProps {
  post: Post;
}

/**
 * The lawsuit card — the single Post display used in the Home feed and on profile pages.
 * Shows the author, title, the accused party, the charges as chips, and the body
 * (truncated with a "Read More" toggle). Read-only: no voting or delete.
 */
const PostCard = ({ post }: PostCardProps) => {
  return (
    <Card>
      <CardContent>
        {/* Author header */}
        <AuthorHeader post={post} />

        <Divider sx={{ my: 2 }} />
        {/* Title, parties, and charges */}
        <PostTitle post={post} />

        <Divider sx={{ my: 2 }} />

        {/* Body */}
        <PostBody post={post} />

        {/* Optional evidence image */}
        {post.image_url && (
          <Box sx={{ mt: 2 }}>
            <CardMedia
              component="img"
              image={post.image_url}
              alt="ראיה מצורפת"
              sx={{ borderRadius: 1, maxHeight: 420, objectFit: "contain", bgcolor: "action.hover" }}
            />
          </Box>
        )}

      </CardContent>
    </Card>
  );
};

export default PostCard;
