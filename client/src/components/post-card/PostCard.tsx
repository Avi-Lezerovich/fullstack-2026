
import { useState } from "react";
import {
  Box,
  Card,
  CardContent,
  CardMedia,
  Divider,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  CircularProgress,
  Alert,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";

import type { Post } from "../../types";
import { deletePost } from "../../api";

import AuthorHeader from "./AuthorHeader";
import PostTitle from "./PostTitle";
import PostBody from "./PostBody";

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
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const isOwner = currentUserId !== undefined && currentUserId === post.author_id;

  const handleDelete = async () => {
    setDeleting(true);
    setError("");
    try {
      await deletePost(post.id);
      setConfirmOpen(false);
      onDeleted?.(post.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "מחיקת התביעה נכשלה");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card>
      <CardContent>
        {/* Author header */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <AuthorHeader post={post} />
          {isOwner && (
            <IconButton
              aria-label="מחק תביעה"
              size="small"
              onClick={() => setConfirmOpen(true)}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          )}
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

      <Dialog open={confirmOpen} onClose={() => (deleting ? null : setConfirmOpen(false))}>
        <DialogTitle>מחיקת תביעה</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          האם אתה בטוח שברצונך למחוק תביעה זו? לא ניתן לשחזר פעולה זו.
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)} disabled={deleting}>ביטול</Button>
          <Button
            onClick={handleDelete}
            variant="contained"
            color="error"
            disabled={deleting}
            startIcon={deleting ? <CircularProgress size={16} /> : null}
          >
            מחק
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default PostCard;
