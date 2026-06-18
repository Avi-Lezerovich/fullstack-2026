import { useEffect, useState } from "react";
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
import { validateImageFile } from "../utils/validationUtils";
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
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => () => {
    if (imagePreviewUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(imagePreviewUrl);
    }
  }, [imagePreviewUrl]);

  const handleChargesChange = (e: SelectChangeEvent<string[]>) => {
    const value = e.target.value;
    setCharges(typeof value === "string" ? value.split(",") : value);
  };

  const clearSelectedImage = () => {
    setImageFile(null);
    if (imagePreviewUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(imagePreviewUrl);
    }
    setImagePreviewUrl(null);
  };

  const handleImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;

    const validationError = validateImageFile(file);
    if (validationError) {
      clearSelectedImage();
      setError(validationError);
      return;
    }

    clearSelectedImage();
    setImageFile(file);
    setImagePreviewUrl(URL.createObjectURL(file));
    setError("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !defendant.trim() || htmlTextLength(body) === 0) {
      setError("נא למלא כותרת, נתבע ותוכן התביעה");
      return;
    }
    if (imageFile) {
      const validationError = validateImageFile(imageFile);
      if (validationError) {
        setError(validationError);
        return;
      }
    }

    setSubmitting(true);
    setError("");
    try {
      let uploadedImageUrl: string | null = null;
      if (imageFile) {
        setUploading(true);
        uploadedImageUrl = (await uploadImage(imageFile)).url;
      }
      await createPost({
        title: title.trim(),
        body,
        defendant: defendant.trim(),
        charges,
        image_url: uploadedImageUrl,
      });
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "הגשת התביעה נכשלה");
    } finally {
      setUploading(false);
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
            <TextField label="שם הנתבע/ת" value={defendant} onChange={(e) => setDefendant(e.target.value)} fullWidth />
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
              <RichTextEditor value={body} onChange={setBody} placeholder="פירוט כתב האישום…" />            </Box>

            <Box>
              <Button
                component="label"
                variant="outlined"
                startIcon={uploading ? <CircularProgress size={16} /> : <ImageIcon />}
                disabled={uploading || submitting}
              >
                {imageFile ? "החלפת הראיה" : "צירוף ראיה"}
                <input hidden type="file" accept="image/*" onChange={handleImage} />
              </Button>
              {imagePreviewUrl && (
                <Box sx={{ position: "relative", mt: 1.5, display: "inline-block" }}>
                  <Box component="img" src={imagePreviewUrl} alt="תצוגה מקדימה" sx={{ maxWidth: "100%", maxHeight: 240, borderRadius: 1, display: "block" }} />
                  <IconButton
                    size="small"
                    onClick={clearSelectedImage}
                    sx={{ position: "absolute", top: 4, insetInlineEnd: 4, bgcolor: "rgba(0,0,0,0.6)", color: "#fff", "&:hover": { bgcolor: "rgba(0,0,0,0.8)" } }}
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Box>
              )}
            </Box>

            <Button type="submit" variant="contained" color="secondary" size="large" disabled={submitting || uploading} startIcon={submitting ? <CircularProgress size={18} /> : <GavelIcon />}>
              {submitting ? "מגיש..." : "הגש תביעה"}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Container>
  );
};

export default NewPost;
