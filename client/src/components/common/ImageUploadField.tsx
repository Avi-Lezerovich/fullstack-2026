import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import * as api from "../../api";
import { ErrorNote } from "./StateViews";

interface Props {
  label: string;
  helper?: string;
  /** The stored URL, or "" for none. Owned by the caller. */
  value: string;
  onChange: (url: string) => void;
  /** Preview size. A profile picture is square; evidence is a wide strip. */
  shape?: "square" | "wide";
  disabled?: boolean;
}

/** Mirrors the server's own list in app/api/uploads.py. */
const ACCEPT = "image/jpeg,image/png,image/gif,image/webp";

/**
 * Pick a file, upload it, keep the URL.
 *
 * The upload happens on selection rather than on form submit, so the person
 * sees the picture they chose before committing to anything — and so a failed
 * upload is reported next to the control that caused it instead of taking the
 * whole form down with it.
 *
 * This replaced a paste-a-URL text field. A URL pointed at somebody else's
 * server: it could rot, change to something else after moderation had already
 * looked at it, or leak every viewer's IP to whoever was hosting it.
 */
const ImageUploadField = ({
  label,
  helper,
  value,
  onChange,
  shape = "wide",
  disabled,
}: Props) => {
  const input = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      onChange(await api.uploadImage(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ההעלאה נכשלה.");
    } finally {
      setBusy(false);
      // Cleared so choosing the same file twice in a row still fires onChange.
      if (input.current) input.current.value = "";
    }
  };

  return (
    <Box>
      <Typography variant="body2" sx={{ mb: 0.5 }}>
        {label}
      </Typography>

      {error && <ErrorNote message={error} />}

      <Stack direction="row" spacing={2} alignItems="flex-start">
        {value && (
          <Box
            component="img"
            src={value}
            alt=""
            data-testid="image-preview"
            sx={{
              width: shape === "square" ? 84 : 140,
              height: 84,
              objectFit: "cover",
              borderRadius: shape === "square" ? "50%" : 1,
              border: "1px solid",
              borderColor: "divider",
              flexShrink: 0,
            }}
          />
        )}

        <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              size="small"
              variant="outlined"
              startIcon={busy ? <CircularProgress size={14} /> : <PhotoCameraIcon />}
              disabled={disabled || busy}
              onClick={() => input.current?.click()}
              data-testid="image-choose"
            >
              {busy ? "מעלה…" : value ? "החלף תמונה" : "בחר תמונה"}
            </Button>

            {value && !busy && (
              <Button
                size="small"
                color="inherit"
                startIcon={<DeleteOutlineIcon />}
                disabled={disabled}
                onClick={() => onChange("")}
                data-testid="image-clear"
              >
                הסר
              </Button>
            )}
          </Stack>

          {helper && (
            <Typography variant="caption" color="text.secondary">
              {helper}
            </Typography>
          )}
        </Stack>
      </Stack>

      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        hidden
        data-testid="image-input"
        onChange={(event) => void choose(event.target.files?.[0])}
      />
    </Box>
  );
}; export default ImageUploadField;
