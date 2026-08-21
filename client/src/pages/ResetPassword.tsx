import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, useSearchParams } from "react-router-dom";

import * as api from "../api";
import { ErrorNote } from "../components/common/StateViews";

const ResetPassword = () => {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (mismatch) return;
    setError(null);
    setBusy(true);
    try {
      await api.confirmPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "איפוס הסיסמה נכשל.");
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <Paper sx={{ p: 3, maxWidth: 440, mx: "auto" }}>
        <ErrorNote message="הקישור אינו תקין — חסר טוקן איפוס." />
        <Link component={RouterLink} to="/forgot-password">
          בקש קישור חדש
        </Link>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 }, maxWidth: 440, mx: "auto" }} component="form" onSubmit={submit}>
      <Typography variant="h4" gutterBottom>
        בחירת סיסמה חדשה
      </Typography>

      {done ? (
        <Stack spacing={2}>
          <Alert severity="success" data-testid="reset-done">
            הסיסמה עודכנה, וכל המכשירים המחוברים נותקו. אפשר להתחבר מחדש.
          </Alert>
          <Button component={RouterLink} to="/login" variant="contained">
            למסך הכניסה
          </Button>
        </Stack>
      ) : (
        <Stack spacing={2}>
          {error && <ErrorNote message={error} />}
          <TextField
            label="סיסמה חדשה"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            fullWidth
            autoComplete="new-password"
            helperText="לפחות 8 תווים"
            inputProps={{ "data-testid": "reset-password", minLength: 8 }}
          />
          <TextField
            label="אימות סיסמה"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            fullWidth
            error={mismatch}
            helperText={mismatch ? "הסיסמאות אינן תואמות" : " "}
            inputProps={{ "data-testid": "reset-confirm" }}
          />
          <Button
            type="submit"
            variant="contained"
            disabled={busy || mismatch}
            data-testid="reset-submit"
          >
            {busy ? "מעדכן…" : "עדכן סיסמה"}
          </Button>
        </Stack>
      )}
    </Paper>
  );
}; export default ResetPassword;
