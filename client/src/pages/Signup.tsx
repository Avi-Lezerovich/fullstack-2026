import { useState } from "react";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, Navigate, useNavigate } from "react-router-dom";

import { ErrorNote } from "../components/common/StateViews";
import { useAuth } from "../context/AuthContext";

/**
 * Signup page - route `/signup`.
 *
 * The limits below mirror the server's (app/validation.py NAME_MIN/NAME_MAX and
 * security.MIN_PASSWORD_LENGTH). They exist to give immediate feedback, not to
 * enforce anything: the server validates independently and its Hebrew message
 * is what gets shown when it disagrees.
 */
const NAME_MIN = 2;
const NAME_MAX = 80;
const MIN_PASSWORD = 8;

const Signup = () => {
  const { user, register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  // Only complain once there is something to compare against, so the field does
  // not sit in an error state while it is still being typed into.
  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (mismatch) return;
    setError(null);
    setBusy(true);
    try {
      // register() signs the new account in as a side effect - the server
      // returns 201 with the session cookie already set - so there is nothing
      // to do here but navigate.
      await register(name.trim(), email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההרשמה נכשלה.");
      setBusy(false);
    }
  };

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 }, maxWidth: 440, mx: "auto" }} component="form" onSubmit={submit}>
      <Typography variant="h4" gutterBottom>
        הרשמה
      </Typography>

      {error && <ErrorNote message={error} />}

      <Stack spacing={2}>
        <TextField
          label="שם מלא"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          fullWidth
          autoFocus
          autoComplete="name"
          inputProps={{ minLength: NAME_MIN, maxLength: NAME_MAX, "data-testid": "signup-name" }}
        />
        <TextField
          label="אימייל"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          fullWidth
          autoComplete="email"
          inputProps={{ "data-testid": "signup-email" }}
        />
        <TextField
          label="סיסמה"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          fullWidth
          autoComplete="new-password"
          helperText={`לפחות ${MIN_PASSWORD} תווים`}
          inputProps={{ minLength: MIN_PASSWORD, "data-testid": "signup-password" }}
        />
        <TextField
          label="אימות סיסמה"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
          fullWidth
          autoComplete="new-password"
          error={mismatch}
          helperText={mismatch ? "הסיסמאות אינן תואמות." : " "}
          inputProps={{ "data-testid": "signup-confirm" }}
        />
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={busy || mismatch}
          data-testid="signup-submit"
        >
          {busy ? "נרשם…" : "הרשמה"}
        </Button>

        <Typography variant="body2" align="center" color="text.secondary">
          כבר יש לך חשבון? <Link component={RouterLink} to="/login">כניסה</Link>
        </Typography>
      </Stack>
    </Paper>
  );
}; export default Signup;
