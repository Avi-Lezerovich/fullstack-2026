import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";

import * as api from "../../api";
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
  /**
   * Text that identifies what is being commented on. Only used to seed an
   * in-character draft, so two different cases do not get the same line.
   */
  assistHint?: string;
}

const CommentComposer = ({
  onSubmit,
  placeholder = "מה יש לך לומר לבית המשפט?",
  submitLabel = "שלח תגובה",
  assistLoad,
  assistHint,
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
        {/* Only once there is something to correct. Unlike the suggestion
            beside it, this one has no case to fall back on — an empty composer
            gives it nothing to work with, and the endpoint answers a blank
            request with a 400. */}
        {body.trim().length > 0 && (
          <AssistButton
            size="small"
            label="תקן לי"
            title="תיקון התגובה"
            helper="בית המשפט יתקן שגיאות כתיב, דקדוק ופיסוק — בלי לשנות את מה שכתבת."
            load={() => api.correctText(body)}
            onAccept={setBody}
            acceptLabel="החלף בטקסט המתוקן"
            busyLabel="מתקן…"
            retryLabel="תקן שוב"
            offlineNote="המנוע המקומי אינו יודע לתקן עברית, ולכן הטקסט הוחזר כפי שהוא. תיקון אמיתי דורש חיבור למודל שפה."
          />
        )}
        {assistLoad && (
          <AssistButton
            size="small"
            label="נסח לי"
            title="הצעה לתגובה"
            helper="בית המשפט מציע נוסח — או שאחת מדמויות החצר תכתוב אותו בקולה. אפשר לערוך לפני השליחה."
            inCharacter
            hint={assistHint}
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
