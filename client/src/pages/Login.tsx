import { useState } from "react";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ErrorNote } from "../components/common/StateViews";
import { useAuth } from "../context/AuthContext";

const Login = () => {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signIn(email.trim(), password);
      // Return the user to whatever they were trying to reach.
      navigate((location.state as { from?: string })?.from ?? "/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההתחברות נכשלה.");
      setBusy(false);
    }
  };

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 }, maxWidth: 440, mx: "auto" }} component="form" onSubmit={submit}>
      <Typography variant="h4" gutterBottom>
        כניסה
      </Typography>

      {error && <ErrorNote message={error} />}

      <Stack spacing={2}>
        <TextField
          label="אימייל"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          fullWidth
          autoComplete="email"
          inputProps={{ "data-testid": "login-email" }}
        />
        <TextField
          label="סיסמה"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          fullWidth
          autoComplete="current-password"
          inputProps={{ "data-testid": "login-password" }}
        />
        <Button
          type="submit"
          variant="contained"
          size="large"
          disabled={busy}
          data-testid="login-submit"
        >
          {busy ? "מתחבר…" : "כניסה"}
        </Button>

        <Typography variant="body2" align="center">
          <Link component={RouterLink} to="/forgot-password">
            שכחתי סיסמה
          </Link>
        </Typography>
        <Typography variant="body2" align="center" color="text.secondary">
          אין לך חשבון? <Link component={RouterLink} to="/signup">הרשמה</Link>
        </Typography>
      </Stack>
    </Paper>
  );
}; export default Login;
