
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
import PostDelete from "./PostDelete";

interface PostCardProps {
  post: Post;
  /** The logged-in user's id, if any — used to only show the delete action on your own posts. */
  currentUserId?: number;
  /** Called after the post is successfully deleted on the server. */
  onDeleted?: (postId: number) => void;
}

/**
 * The lawsuit card — the single Post display used in the Home feed and on profile pages.
 * Shows the author, title, the accused party, the charges as chips, and the body
 * (truncated with a "Read More" toggle). Voting is still unsupported; the post's own
 * author can delete it (with confirmation) via the trash icon.
 */
const PostCard = ({ post, currentUserId, onDeleted }: PostCardProps) => {
  return (
    <Card data-testid="post-card">
      <CardContent>
        {/* Author header */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <AuthorHeader post={post} />
          <PostDelete post={post} currentUserId={currentUserId} onDeleted={onDeleted} />
        </Box>

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
