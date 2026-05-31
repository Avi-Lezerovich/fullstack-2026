import { useState } from "react";
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField,
  Stack, Avatar, Box, CircularProgress, Alert,
} from "@mui/material";
import ImageIcon from "@mui/icons-material/Image";

import { updateProfile, uploadImage } from "../../api";
import { getInitials } from "../../utils/stringUtils";
import type { User } from "../../types";

type Props = {
  open: boolean;
  user: User;
  onClose: () => void;
  onSaved: (user: User) => void;
};

/** Dialog for editing the logged-in user's bio and avatar. */
const EditProfileDialog = ({ open, user, onClose, onSaved }: Props) => {
  const [bio, setBio] = useState(user.bio || "");
  const [avatarUrl, setAvatarUrl] = useState<string | null>(user.avatar_url || null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleAvatar = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const { url } = await uploadImage(file);
      setAvatarUrl(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "העלאת התמונה נכשלה");
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const { user: updated } = await updateProfile({ bio, avatar_url: avatarUrl ?? "" });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "שמירת הפרופיל נכשלה");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>עריכת פרופיל</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={3} sx={{ mt: 1 }} alignItems="flex-start">
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Avatar src={avatarUrl || undefined} sx={{ width: 72, height: 72, bgcolor: "primary.main", color: "background.default", fontWeight: 700 }}>
              {getInitials(user.name)}
            </Avatar>
            <Button component="label" variant="outlined" startIcon={uploading ? <CircularProgress size={16} /> : <ImageIcon />} disabled={uploading}>
              {avatarUrl ? "החלף תמונה" : "העלה תמונת פרופיל"}
              <input hidden type="file" accept="image/*" onChange={handleAvatar} />
            </Button>
          </Box>
          <TextField
            label="אודות"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            fullWidth
            multiline
            minRows={3}
            placeholder="כמה מילים עליך…"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>ביטול</Button>
        <Button onClick={handleSave} variant="contained" color="secondary" disabled={saving || uploading} startIcon={saving ? <CircularProgress size={16} /> : null}>
          שמור
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default EditProfileDialog;
