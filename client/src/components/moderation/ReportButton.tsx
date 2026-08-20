import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import FlagOutlinedIcon from "@mui/icons-material/FlagOutlined";

import * as api from "../../api";
import { ErrorNote } from "../common/StateViews";
import { REPORT_REASONS } from "../../types";

interface Props {
  targetType: "case" | "comment";
  targetId: number;
  size?: "small" | "medium";
}

/**
 * The human half of the hybrid moderation system: anyone can flag anything,
 * and a moderator bot picks it up on the next tick.
 */
export default function ReportButton({ targetType, targetId, size = "small" }: Props) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string>(REPORT_REASONS[0].value);
  const [details, setDetails] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.reportContent(targetType, targetId, reason, details || undefined);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "לא הצלחנו לשלוח את הדיווח.");
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    setOpen(false);
    // Reset only after closing, so the confirmation is readable first.
    setTimeout(() => {
      setDone(false);
      setDetails("");
      setError(null);
    }, 200);
  };

  return (
    <>
      <Button
        size={size}
        color="inherit"
        startIcon={<FlagOutlinedIcon fontSize="small" />}
        onClick={() => setOpen(true)}
        data-testid="report-button"
      >
        דווח
      </Button>

      <Dialog open={open} onClose={close} fullWidth maxWidth="xs">
        <DialogTitle>דיווח על תוכן</DialogTitle>
        <DialogContent>
          {done ? (
            <Alert severity="success" data-testid="report-sent">
              הדיווח התקבל ויטופל על ידי צוות הפיקוח.
            </Alert>
          ) : (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {error && <ErrorNote message={error} />}
              <TextField
                select
                label="סיבת הדיווח"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                fullWidth
              >
                {REPORT_REASONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="פרטים (אופציונלי)"
                value={details}
                onChange={(e) => setDetails(e.target.value)}
                multiline
                minRows={2}
                fullWidth
                inputProps={{ maxLength: 1000 }}
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>{done ? "סגור" : "ביטול"}</Button>
          {!done && (
            <Button onClick={submit} variant="contained" disabled={busy} data-testid="report-submit">
              {busy ? "שולח…" : "שלח דיווח"}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
}
