import { useState } from "react";
import { Link as RouterLink, Navigate, useNavigate } from "react-router-dom";
import { Container, Paper, TextField, Button, Typography, Box, Alert, Stack, Link, CircularProgress } from "@mui/material";
import HowToRegIcon from "@mui/icons-material/HowToReg";

import { isLoggedIn, signup, saveSession } from "../api";
import { EMAIL_RE, MIN_PASSWORD } from "../utils/validationUtils";

/**
 * Signup page — route `/signup`.
 * Plain useState form: validate, create the account, save the session, go home.
 * Already-logged-in visitors are bounced to "/".
 */
const Signup = () => {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isLoggedIn()) return <Navigate to="/" replace />;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("נא להזין שם מלא");
      return;
    }
    if (!EMAIL_RE.test(email)) {
      setError("כתובת אימייל לא תקינה");
      return;
    }
    if (password.length < MIN_PASSWORD) {
      setError(`הסיסמה חייבת להכיל לפחות ${MIN_PASSWORD} תווים`);
      return;
    }
    if (password !== confirm) {
      setError("הסיסמאות אינן תואמות");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const res = await signup(name, email, password);
      saveSession(res.token, res.user);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההרשמה נכשלה");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper sx={{ p: 5 }}>
        <Box sx={{ textAlign: "center", mb: 3 }}>
          <Typography variant="h4" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, color: "primary.dark" }}>
            רישום לרשימת התובעים
          </Typography>
          <Typography sx={{ color: "text.secondary", mt: 0.5 }}>
            רישום קצר. תסכולים אינסופיים.
          </Typography>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <Stack spacing={2}>
            <TextField label="שם מלא" value={name} onChange={(e) => setName(e.target.value)} fullWidth autoComplete="name" autoFocus />
            <TextField label="אימייל" type="email" value={email} onChange={(e) => setEmail(e.target.value)} fullWidth autoComplete="email" />
            <TextField label="סיסמה" type="password" value={password} onChange={(e) => setPassword(e.target.value)} fullWidth autoComplete="new-password" helperText={`לפחות ${MIN_PASSWORD} תווים`} />
            <TextField label="אימות סיסמה" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} fullWidth autoComplete="new-password" />
            <Button type="submit" variant="contained" color="secondary" size="large" disabled={submitting} startIcon={submitting ? <CircularProgress size={18} /> : <HowToRegIcon />}>
              {submitting ? "רושם..." : "הצטרף לרשימת המושבעים"}
            </Button>
          </Stack>
        </Box>

        <Typography sx={{ textAlign: "center", mt: 3, color: "text.secondary" }}>
          כבר רשום?{" "}
          <Link component={RouterLink} to="/login" sx={{ fontWeight: 700, color: "primary.main" }}>
            התייצב באולם
          </Link>
        </Typography>
      </Paper>
    </Container>
  );
};

export default Signup;
