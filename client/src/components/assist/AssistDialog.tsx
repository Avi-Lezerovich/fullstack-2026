import { useCallback, useEffect, useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import RefreshIcon from "@mui/icons-material/Refresh";

import { ErrorNote, Loading } from "../common/StateViews";

interface Props {
  open: boolean;
  title: string;
  helper?: string;
  /** Calls whichever `/api/assist/*` endpoint this dialog is for. */
  load: () => Promise<{ body: string; backend: string }>;
  onClose: () => void;
  /** The user accepted the text — possibly after editing it. */
  onAccept: (text: string) => void;
  acceptLabel?: string;
}

const BACKEND_LABELS: Record<string, string> = {
  llm: "נוסח על ידי בינה מלאכותית",
  offline: "נוסח על ידי מנסח בית המשפט (מנוע מקומי)",
};

/**
 * The writing-help dialog: generate, edit, accept.
 *
 * Nothing here submits anything. The suggestion lands back in the composer the
 * user was already filling in, so the text still goes through the ordinary
 * publish path — including the moderation scan — exactly like text they typed
 * themselves.
 */
const AssistDialog = ({
  open,
  title,
  helper,
  load,
  onClose,
  onAccept,
  acceptLabel = "השתמש בנוסח",
}: Props) => {
  const [text, setText] = useState("");
  const [backend, setBackend] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const generate = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await load();
      setText(result.body);
      setBackend(result.backend);
    } catch (err) {
      setError(err instanceof Error ? err.message : "לא הצלחנו לנסח כרגע.");
    } finally {
      setBusy(false);
    }
  }, [load]);

  // Generate as the dialog opens; a closed dialog holds no stale draft.
  useEffect(() => {
    if (!open) {
      setText("");
      setBackend(null);
      setError(null);
      return;
    }
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="assist-dialog">
      <DialogTitle>
        <Stack direction="row" spacing={1} alignItems="center">
          <AutoAwesomeIcon color="secondary" fontSize="small" />
          <span>{title}</span>
        </Stack>
      </DialogTitle>

      <DialogContent>
        {helper && (
          <Typography color="text.secondary" variant="body2" sx={{ mb: 1.5 }}>
            {helper}
          </Typography>
        )}

        {error && <ErrorNote message={error} />}
        {busy && !text && <Loading label="מנסח…" />}

        {(text || !busy) && (
          <TextField
            value={text}
            onChange={(e) => setText(e.target.value)}
            multiline
            minRows={6}
            fullWidth
            sx={{ mt: 1 }}
            inputProps={{ "data-testid": "assist-text", maxLength: 8000 }}
          />
        )}

        {backend && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
            {BACKEND_LABELS[backend] ?? backend}
            {backend === "offline" && " · אותו קלט מפיק תמיד את אותו נוסח, אז שינוי הפרטים ייתן נוסח אחר"}
          </Typography>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>ביטול</Button>
        <Button startIcon={<RefreshIcon />} onClick={() => void generate()} disabled={busy}>
          נסח מחדש
        </Button>
        <Button
          variant="contained"
          color="secondary"
          disabled={busy || !text.trim()}
          onClick={() => {
            onAccept(text.trim());
            onClose();
          }}
          data-testid="assist-accept"
        >
          {acceptLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}; export default AssistDialog;
