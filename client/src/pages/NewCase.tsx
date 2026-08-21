import { useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useNavigate } from "react-router-dom";

import * as api from "../api";
import AssistButton from "../components/assist/AssistButton";
import { ErrorNote } from "../components/common/StateViews";
import { CHARGE_SUGGESTIONS } from "../types";
import type { User } from "../types";

const NewCase = () => {
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [defendantText, setDefendantText] = useState("");
  const [charges, setCharges] = useState<string[]>([]);
  const [defendantUser, setDefendantUser] = useState<User | null>(null);
  const [candidates, setCandidates] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const searchDefendants = async (text: string) => {
    if (text.trim().length < 2) {
      setCandidates([]);
      return;
    }
    try {
      const { users } = await api.fetchUsers({ search: text, limit: 8 });
      setCandidates(users);
    } catch {
      setCandidates([]);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const created = await api.createCase({
        title,
        body,
        defendant_text: defendantText || defendantUser?.name || "",
        defendant_user_id: defendantUser?.id ?? null,
        charges,
      });
      navigate(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "לא הצלחנו להגיש את התביעה.");
      setSaving(false);
    }
  };

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }} component="form" onSubmit={submit}>
      <Typography variant="h4" gutterBottom>
        הגשת תביעה
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        אפשר לתבוע משתמש רשום — ואז גם הוא יוכל לזמן עדים — או כל דבר אחר בעולם, למשל "יום שני".
      </Typography>

      {error && <ErrorNote message={error} />}

      <Stack spacing={2.5}>
        <TextField
          label="כותרת התביעה"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          fullWidth
          helperText="לדוגמה: התביעה נגד יום שני"
          inputProps={{ "data-testid": "case-title", maxLength: 512 }}
        />

        <Autocomplete
          options={candidates}
          value={defendantUser}
          getOptionLabel={(option) => option.name}
          onInputChange={(_, text) => void searchDefendants(text)}
          onChange={(_, value) => {
            setDefendantUser(value);
            if (value) setDefendantText(value.name);
          }}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          noOptionsText="לא נמצאו משתמשים"
          renderInput={(params) => (
            <TextField
              {...params}
              label="נתבע רשום (אופציונלי)"
              helperText="השאר ריק כדי לתבוע משהו שאינו משתמש"
            />
          )}
        />

        <TextField
          label="נגד מי התביעה"
          value={defendantText}
          onChange={(e) => setDefendantText(e.target.value)}
          required
          fullWidth
          inputProps={{ "data-testid": "case-defendant", maxLength: 255 }}
        />

        <Autocomplete
          multiple
          freeSolo
          options={[...CHARGE_SUGGESTIONS]}
          value={charges}
          onChange={(_, value) => setCharges(value.slice(0, 5))}
          renderTags={(value, getTagProps) =>
            value.map((option, index) => (
              <Chip label={option} size="small" {...getTagProps({ index })} key={option} />
            ))
          }
          renderInput={(params) => (
            <TextField {...params} label="סעיפי האישום" helperText="עד חמישה סעיפים" />
          )}
        />

        <Box>
          <TextField
            label="כתב התביעה"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
            multiline
            minRows={6}
            fullWidth
            inputProps={{ "data-testid": "case-body", maxLength: 8000 }}
          />
          <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 1 }}>
            {/* Needs at least a defendant — the drafter has nothing to write
                about otherwise, and the endpoint says so with a 400. */}
            <AssistButton
              size="small"
              label="נסח לי את התביעה"
              title="ניסוח כתב התביעה"
              helper="מנסח בית המשפט יכתוב טיוטה מהפרטים שמילאת. אפשר לערוך אותה לפני ההגשה."
              disabled={!defendantText.trim() && !title.trim()}
              load={() =>
                api.draftLawsuit({
                  defendant_text: defendantText,
                  title,
                  charges,
                  hint: body,
                })
              }
              onAccept={setBody}
              acceptLabel="הכנס לכתב התביעה"
            />
          </Box>
        </Box>

        <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
          <Button onClick={() => navigate(-1)} disabled={saving}>
            ביטול
          </Button>
          <Button
            type="submit"
            variant="contained"
            color="secondary"
            disabled={saving}
            data-testid="case-submit"
          >
            {saving ? "מגיש…" : "הגש לבית המשפט"}
          </Button>
        </Box>
      </Stack>
    </Paper>
  );
}; export default NewCase;
