import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import * as api from "../../api";
import { ErrorNote } from "../common/StateViews";
import { DOC_FONT } from "../../theme";

interface Props {
  caseId: number;
  onTestified: () => void;
}

/**
 * Shown only when the server says `viewer.can_testify` — i.e. you were
 * summoned, have not answered, and the witness phase is still open. The client
 * never works that out for itself.
 */
const TestifyForm = ({ caseId, onTestified }: Props) => {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!body.trim()) return;
    setError(null);
    setBusy(true);
    try {
      await api.testify(caseId, body.trim());
      setBody("");
      onTestified();
    } catch (err) {
      setError(err instanceof Error ? err.message : "לא הצלחנו למסור את העדות.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper
      sx={{ p: { xs: 2, sm: 3 }, borderInlineStart: "4px solid", borderColor: "info.main" }}
      component="form"
      onSubmit={submit}
      data-testid="testify-form"
    >
      <Typography variant="h6" gutterBottom>
        זומנת למסור עדות
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        העדות תיווסף לפרוטוקול הדיון ותוצג לחבר המושבעים. אפשר למסור עדות אחת בלבד.
      </Alert>

      {error && <ErrorNote message={error} />}

      <TextField
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="ספר/י לבית המשפט מה ראית…"
        multiline
        minRows={3}
        fullWidth
        inputProps={{ "data-testid": "testify-body", maxLength: 4000 }}
        sx={{ fontFamily: DOC_FONT }}
      />

      <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 1.5 }}>
        <Button
          type="submit"
          variant="contained"
          disabled={busy || !body.trim()}
          data-testid="testify-submit"
        >
          {busy ? "מוסר…" : "מסור עדות"}
        </Button>
      </Box>
    </Paper>
  );
}; export default TestifyForm;
