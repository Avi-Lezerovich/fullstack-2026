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
  const [bio, setBio] = useState("");
  const [saving, setSaving] = useState(false);

  if (profile.loading) return <Loading />;
  if (profile.error) return <ErrorNote message={profile.error} />;
  if (!profile.data) return <ErrorNote message="המשתמש לא נמצא." />;

  const person = profile.data;
  const isMe = me?.id === person.id;

  const openEditor = () => {
    setBio(person.bio ?? "");
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const { user: updated } = await api.updateMyProfile({ bio });
      setUser(updated);
      await profile.reload();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

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
          <TextField
            label="קצת עליי"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            multiline
            minRows={3}
            fullWidth
            sx={{ mt: 1 }}
            inputProps={{ maxLength: 500 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(false)}>ביטול</Button>
          <Button onClick={save} variant="contained" disabled={saving}>
            {saving ? "שומר…" : "שמירה"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}; export default Profile;
