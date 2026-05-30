import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Container, Paper, Box, Stack, Typography, TextField, Button, Alert, CircularProgress,
  Select, MenuItem, FormControl, InputLabel, Chip, OutlinedInput, IconButton,
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";
import ImageIcon from "@mui/icons-material/Image";
import CloseIcon from "@mui/icons-material/Close";

import { createPost, uploadImage } from "../api";
import { CHARGES_OPTIONS } from "../types";
import { htmlTextLength } from "../utils/htmlUtils";
import RichTextEditor from "../components/editor/RichTextEditor";

/**
 * New lawsuit page — route `/new-post` (guarded by ProtectedRoute).
 * Title, the accused, charges, a WYSIWYG body, and an optional evidence image.
 * On submit we create the post and navigate back to the feed.
 */
const NewPost = () => {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [defendant, setDefendant] = useState("");
  const [charges, setCharges] = useState<string[]>([]);
  const [body, setBody] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleChargesChange = (e: SelectChangeEvent<string[]>) => {
    const value = e.target.value;
    setCharges(typeof value === "string" ? value.split(",") : value);
  };

  const handleImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const { url } = await uploadImage(file);
      setImageUrl(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "העלאת התמונה נכשלה");
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !defendant.trim() || htmlTextLength(body) === 0) {
      setError("נא למלא כותרת, נתבע ותוכן התביעה");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await createPost({
        title: title.trim(),
        body,
        defendant: defendant.trim(),
        charges,
        image_url: imageUrl,
      });
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

            <Box>
              <Typography variant="body2" sx={{ mb: 0.5, color: "text.secondary" }}>תוכן התביעה</Typography>
              <RichTextEditor value={body} onChange={setBody} placeholder="פרט את כתב האישום…" />
            </Box>

            {/* Optional evidence image */}
            <Box>
              <Button
                component="label"
                variant="outlined"
                startIcon={uploading ? <CircularProgress size={16} /> : <ImageIcon />}
                disabled={uploading}
              >
                {imageUrl ? "החלף ראיה (תמונה)" : "צרף ראיה (תמונה)"}
                <input hidden type="file" accept="image/*" onChange={handleImage} />
              </Button>
              {imageUrl && (
                <Box sx={{ position: "relative", mt: 1.5, display: "inline-block" }}>
                  <Box component="img" src={imageUrl} alt="תצוגה מקדימה" sx={{ maxWidth: "100%", maxHeight: 240, borderRadius: 1, display: "block" }} />
                  <IconButton
                    size="small"
                    onClick={() => setImageUrl(null)}
                    sx={{ position: "absolute", top: 4, insetInlineEnd: 4, bgcolor: "rgba(0,0,0,0.6)", color: "#fff", "&:hover": { bgcolor: "rgba(0,0,0,0.8)" } }}
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Box>
              )}
            </Box>

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
