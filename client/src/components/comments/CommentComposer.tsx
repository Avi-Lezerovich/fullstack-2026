import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";

import AssistButton from "../assist/AssistButton";
import { ErrorNote } from "../common/StateViews";

interface Props {
  onSubmit: (body: string) => Promise<void>;
  placeholder?: string;
  submitLabel?: string;
  /**
   * When given, a "נסח לי" button appears and drops the suggestion straight
   * into this composer's field. The composer owns the text either way, so the
   * caller does not have to lift state just to offer writing help.
   */
  assistLoad?: () => Promise<{ body: string; backend: string }>;
}

const CommentComposer = ({
  onSubmit,
  placeholder = "מה יש לך לומר לבית המשפט?",
  submitLabel = "שלח תגובה",
  assistLoad,
}: Props) => {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!body.trim()) return;

    setError(null);
    setBusy(true);
    try {
      await onSubmit(body.trim());
      setBody("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "לא הצלחנו לשלוח את התגובה.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box component="form" onSubmit={submit}>
      {error && <ErrorNote message={error} />}
      <TextField
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={placeholder}
        multiline
        minRows={2}
        fullWidth
        size="small"
        inputProps={{ "data-testid": "comment-body", maxLength: 4000 }}
      />
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, mt: 1 }}>
        {assistLoad && (
          <AssistButton
            size="small"
            label="נסח לי"
            title="הצעה לתגובה"
            helper="בית המשפט מציע נוסח. אפשר לערוך אותו לפני השליחה."
            load={assistLoad}
            onAccept={setBody}
            acceptLabel="הכנס לתגובה"
          />
        )}
        <Button
          type="submit"
          variant="contained"
          size="small"
          disabled={busy || !body.trim()}
          data-testid="comment-submit"
        >
          {busy ? "שולח…" : submitLabel}
        </Button>
      </Box>
    </Box>
  );
}; export default CommentComposer;
