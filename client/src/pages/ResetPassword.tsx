import { useCallback, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, useSearchParams } from "react-router-dom";

import * as api from "../api";
import { ErrorPage } from "../components/common/ErrorPage";
import { ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";

const ResetPassword = () => {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  // The link is checked before the form is drawn. Rejecting rather than
  // returning early keeps the hook order fixed, and spares the server a round
  // trip for a URL with no token in it at all.
  const load = useCallback(
    () => (token ? api.validatePasswordReset(token) : Promise.reject(new Error("no token"))),
    [token],
  );
  const check = useAsync(load, [token]);

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

  if (check.loading) return <Loading label="בודק את הקישור…" />;

  // Missing, forged, expired, already spent: one page for all four. The
  // server refuses to say which, and the client must not become the oracle
  // the server declined to be — so `check.error` is not shown.
  if (check.error) {
    return (
      <ErrorPage
        code="410"
        title="צו האיפוס פג תוקפו"
        description="הקישור תקף לזמן קצר בלבד וניתן לשימוש חד־פעמי. הקישור הזה כבר נוצל או שחלף זמנו."
        action={
          <Button
            component={RouterLink}
            to="/forgot-password"
            variant="contained"
            data-testid="reset-request-new"
          >
            בקשת קישור חדש
          </Button>
        }
      />
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
