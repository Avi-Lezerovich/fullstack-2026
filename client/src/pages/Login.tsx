import { useState } from "react";
import { Link as RouterLink, Navigate, useNavigate } from "react-router-dom";
import { Container, Paper, TextField, Button, Typography, Box, Alert, Stack, Link, CircularProgress } from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";

import { isLoggedIn, login, saveSession } from "../api";
import { EMAIL_RE } from "../utils/validationUtils";

/**
 * Login page — route `/login`.
 * Plain useState form: validate the email, call the API, save the session, go home.
 * Already-logged-in visitors are bounced to "/".
 */
const Login = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isLoggedIn()) return <Navigate to="/" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!EMAIL_RE.test(email)) {
      setError("כתובת אימייל לא תקינה");
      return;
    }
    if (!password) {
      setError("נא להזין סיסמה");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const res = await login(email, password);
      saveSession(res.user);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההתחברות נכשלה");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper sx={{ p: 5 }}>
        <Box sx={{ textAlign: "center", mb: 3 }}>
        <Typography variant="h4" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, color: "primary.dark" }}>
            התייצבות בפני בית המשפט
          </Typography>
          <Typography sx={{ color: "text.secondary", mt: 0.5 }}>
            יש להזדהות כדי להגיש תביעות
          </Typography>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <Stack spacing={2.5}>
            <TextField label="אימייל" type="email" value={email} onChange={(e) => setEmail(e.target.value)} fullWidth autoComplete="email" autoFocus />
            <TextField label="סיסמה" type="password" value={password} onChange={(e) => setPassword(e.target.value)} fullWidth autoComplete="current-password" />
            <Button type="submit" variant="contained" color="secondary" size="large" disabled={submitting} startIcon={submitting ? <CircularProgress size={18} /> : <GavelIcon />}>
            {submitting ? "בתהליך התייצבות..." : "התייצבות"}              {/* {submitting ? "מתייצב..." : "התייצב בפני בית המשפט"} --- IGNORE --- */}
            </Button>
          </Stack>
        </Box>

          <Typography sx={{ textAlign: "center", mt: 3, color: "text.secondary" }}>
          רוצה להצטרף כתובע/ת?{" "}
          <Link component={RouterLink} to="/signup" sx={{ fontWeight: 700, color: "primary.main" }}>
            הרשמה
          </Link>
        </Typography>
      </Paper>
    </Container>
  );
};

export default Login;
