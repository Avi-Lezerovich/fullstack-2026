import { useCallback, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { Link as RouterLink, useParams } from "react-router-dom";

import * as api from "../api";
import CaseCard from "../components/feed/CaseCard";
import { CourtRecord, MyMemories } from "../components/common/CourtRecord";
import ImageUploadField from "../components/common/ImageUploadField";
import { EmptyState, ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../context/AuthContext";
import { formatDate, initials } from "../utils/format";

const Profile = () => {
  const { userId } = useParams();
  const id = Number(userId);
  const { user: me, setUser } = useAuth();

  const loadProfile = useCallback(() => api.fetchUser(id), [id]);
  const loadCases = useCallback(() => api.fetchCases({ author_id: id, limit: 20 }), [id]);

  const profile = useAsync(loadProfile, [id]);
  const cases = useAsync(loadCases, [id]);

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (profile.loading) return <Loading />;
  if (profile.error) return <ErrorNote message={profile.error} />;
  if (!profile.data) return <ErrorNote message="המשתמש לא נמצא." />;

  const person = profile.data;
  const isMe = me?.id === person.id;

  const openEditor = () => {
    setName(person.name);
    setBio(person.bio ?? "");
    setAvatarUrl(person.avatar_url ?? "");
    setSaveError(null);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      // All three go in one PATCH; the endpoint has always accepted them and
      // only `bio` was ever being sent, so nobody could change their display
      // name or set a picture.
      const { user: updated } = await api.updateMyProfile({
        name: name.trim(),
        bio,
        avatar_url: avatarUrl,
      });
      setUser(updated);
      await profile.reload();
      setEditing(false);
    } catch (err) {
      // The server validates the name independently and answers in Hebrew.
      setSaveError(err instanceof Error ? err.message : "השמירה נכשלה.");
    } finally {
      setSaving(false);
    }
  };

  const nameTooShort = name.trim().length < 2;

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
          <Avatar
            src={person.avatar_url ?? undefined}
            sx={{ width: 72, height: 72, fontSize: "1.5rem" }}
          >
            {initials(person.name)}
          </Avatar>

          <Box sx={{ flex: 1, textAlign: { xs: "center", sm: "start" } }}>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              justifyContent={{ xs: "center", sm: "flex-start" }}
            >
              <Typography variant="h5">{person.name}</Typography>
              {person.is_bot && (
                <Chip icon={<SmartToyIcon />} label="בוט בית משפט" size="small" variant="outlined" />
              )}
              {person.is_admin && <Chip label="מנהל" size="small" color="primary" />}
            </Stack>

            {person.bio && (
              <Typography color="text.secondary" sx={{ mt: 0.5 }}>
                {person.bio}
              </Typography>
            )}
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              {person.case_count} תביעות · הצטרף/ה {formatDate(person.created_at)}
            </Typography>
          </Box>

          {isMe ? (
            <Button onClick={openEditor}>עריכת פרופיל</Button>
          ) : (
            me && (
              <Button
                variant="outlined"
                startIcon={<MailOutlineIcon />}
                component={RouterLink}
                to={`/messages?to=${person.id}`}
                data-testid="message-user"
              >
                שלח/י הודעה
              </Button>
            )
          )}
        </Stack>
      </Paper>

      {/* A bot's own history, and - if this is your page - the file the court
          keeps on you. Both were readable from the API and from nowhere else,
          which made the "forget me" endpoint a feature only curl users had. */}
      {person.is_bot && <CourtRecord userId={person.id} />}
      {isMe && <MyMemories />}

      <Typography variant="h6">התביעות שהוגשו</Typography>

      {cases.loading && <Loading />}
      {cases.error && <ErrorNote message={cases.error} />}
      {!cases.loading && (cases.data?.cases.length ?? 0) === 0 && (
        <EmptyState title="עדיין לא הוגשו תביעות" />
      )}
      {cases.data?.cases.map((c) => (
        <CaseCard key={c.id} case={c} />
      ))}

      <Dialog open={editing} onClose={() => setEditing(false)} fullWidth maxWidth="sm">
        <DialogTitle>עריכת פרופיל</DialogTitle>
        <DialogContent>
          {saveError && <ErrorNote message={saveError} />}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="שם מלא"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              required
              error={nameTooShort}
              helperText={nameTooShort ? "השם חייב להכיל לפחות שני תווים." : " "}
              inputProps={{ maxLength: 80, "data-testid": "profile-name" }}
            />
            <ImageUploadField
              label="תמונת פרופיל"
              helper="JPG, PNG, GIF או WEBP, עד 5 מגה-בייט. בלי תמונה יוצגו ראשי התיבות של שמך."
              value={avatarUrl}
              onChange={setAvatarUrl}
              shape="square"
              disabled={saving}
            />
            <TextField
              label="קצת עליי"
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              multiline
              minRows={3}
              fullWidth
              inputProps={{ maxLength: 500, "data-testid": "profile-bio" }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(false)}>ביטול</Button>
          <Button
            onClick={save}
            variant="contained"
            disabled={saving || nameTooShort}
            data-testid="profile-save"
          >
            {saving ? "שומר…" : "שמירה"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}; export default Profile;
