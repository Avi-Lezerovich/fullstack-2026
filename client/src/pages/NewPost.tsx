import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Container, Paper, Box, Stack, Typography, TextField, Button, Alert, CircularProgress,
  Select, MenuItem, FormControl, InputLabel, Chip, OutlinedInput,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";

import { createPost } from "../api";
import { CHARGES_OPTIONS } from "../types";

/**
 * New lawsuit page — route `/new-post` (guarded by ProtectedRoute).
 * A single form: title, the accused, charges, and the body. On submit we create
 * the post and navigate back to the feed.
 */
const NewPost = () => {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [defendant, setDefendant] = useState("");
  const [charges, setCharges] = useState<string[]>([]);
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleChargesChange = (e: SelectChangeEvent<string[]>) => {
    const value = e.target.value;
    setCharges(typeof value === "string" ? value.split(",") : value);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !defendant.trim() || !body.trim()) {
      setError("נא למלא כותרת, נתבע ותוכן התביעה");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await createPost({ title: title.trim(), body: body.trim(), defendant: defendant.trim(), charges });
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "הגשת התביעה נכשלה");
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="sm" sx={{ py: 4 }}>
      <Box sx={{ mb: 3, textAlign: "center" }}>
        <Typography variant="h3" component="h1" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 900, color: "primary.dark" }}>
          הגשת תביעה
        </Typography>
        <Typography sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic" }}>
          מלא את כתב האישום בקפדנות. הקהילה תכריע.
        </Typography>
      </Box>

      <Paper sx={{ p: 4 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <Stack spacing={2.5}>
            <TextField label="כותרת התביעה" value={title} onChange={(e) => setTitle(e.target.value)} fullWidth autoFocus />
            <TextField label="הנתבע" value={defendant} onChange={(e) => setDefendant(e.target.value)} fullWidth />

            <FormControl fullWidth>
              <InputLabel id="charges-label">סעיפי אישום</InputLabel>
              <Select
                labelId="charges-label"
                multiple
                value={charges}
                onChange={handleChargesChange}
                input={<OutlinedInput label="סעיפי אישום" />}
                renderValue={(selected) => (
                  <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value} size="small" />
                    ))}
                  </Stack>
                )}
              >
                {CHARGES_OPTIONS.map((charge) => (
                  <MenuItem key={charge} value={charge}>{charge}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField label="תוכן התביעה" value={body} onChange={(e) => setBody(e.target.value)} fullWidth multiline minRows={5} />

            <Button type="submit" variant="contained" color="secondary" size="large" disabled={submitting} startIcon={submitting ? <CircularProgress size={18} /> : <GavelIcon />}>
              {submitting ? "מגיש..." : "הגש תביעה"}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Container>
  );
};

export default NewPost;
