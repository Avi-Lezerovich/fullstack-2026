import { useState } from "react";
import {
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

interface PostDeleteProps {
  post: Post;
  /** The logged-in user's id, if any — used to only show the delete action on your own posts. */
  currentUserId?: number;
  /** Called after the post is successfully deleted on the server. */
  onDeleted?: (postId: number) => void;
}

/**
 * Delete action for a post: a trash icon (shown only to the post's own author)
 * that opens a confirm dialog before calling the delete API.
 */
const PostDelete = ({ post, currentUserId, onDeleted }: PostDeleteProps) => {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const isOwner = currentUserId !== undefined && currentUserId === post.author_id;

  if (!isOwner) return null;

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
    <>
      <IconButton
        aria-label="מחק תביעה"
        size="small"
        onClick={() => setConfirmOpen(true)}
        data-testid="post-delete-button"
      >
        <DeleteIcon fontSize="small" />
      </IconButton>

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
            data-testid="post-delete-confirm"
          >
            מחק
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default PostDelete;
