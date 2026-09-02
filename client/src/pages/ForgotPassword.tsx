import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../api";

const ForgotPassword = () => {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.requestPasswordReset(email.trim());
    } finally {
      // The server answers identically whether or not the address is
      // registered, and so does this page — otherwise the UI would leak
      // exactly what the API is careful not to.
      setSent(true);
      setBusy(false);
    }
  };

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 }, maxWidth: 440, mx: "auto" }} component="form" onSubmit={submit}>
      <Typography variant="h4" gutterBottom>
        איפוס סיסמה
      </Typography>

      {sent ? (
        <Stack spacing={2}>
          <Alert severity="success" data-testid="reset-requested">
            אם הכתובת רשומה במערכת, נשלח אליה קישור לאיפוס הסיסמה. הקישור תקף ל-30 דקות.
          </Alert>
          <Typography variant="body2" color="text.secondary">
            לא הגיע? כדאי לבדוק גם בתיקיית הספאם.
          </Typography>
          <Link component={RouterLink} to="/login">
            חזרה לכניסה
          </Link>
        </Stack>
      ) : (
        <Stack spacing={2}>
          <Typography color="text.secondary">
            הזן את כתובת האימייל שלך ונשלח אליך קישור לבחירת סיסמה חדשה.
          </Typography>
          <TextField
            label="אימייל"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            fullWidth
            autoComplete="email"
            inputProps={{ "data-testid": "forgot-email" }}
          />
          <Button type="submit" variant="contained" disabled={busy} data-testid="forgot-submit">
            {busy ? "שולח…" : "שלח קישור לאיפוס"}
          </Button>
          <Typography variant="body2" align="center">
            <Link component={RouterLink} to="/login">
              חזרה לכניסה
            </Link>
          </Typography>
        </Stack>
      )}
    </Paper>
  );
}; export default ForgotPassword;
