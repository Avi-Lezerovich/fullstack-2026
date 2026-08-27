import { useCallback, useEffect, useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import RefreshIcon from "@mui/icons-material/Refresh";

import * as api from "../../api";
import { ErrorNote, Loading } from "../common/StateViews";
import { AGENT_ROLE_LABELS, type CourtAgent } from "../../types";

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
  /**
   * Offer the court's own personalities as authors. The roster comes from
   * /api/agents and each choice routes to /assist/in-character instead of the
   * house drafter.
   */
  inCharacter?: boolean;
  /** Seeds an in-character draft, so two cases do not get identical text. */
  hint?: string;
}

/** The roster changes only when the database is re-seeded; fetch it once. */
let voiceCache: CourtAgent[] | null = null;

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
  inCharacter = false,
  hint = "",
}: Props) => {
  const [text, setText] = useState("");
  const [backend, setBackend] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [voices, setVoices] = useState<CourtAgent[]>(voiceCache ?? []);
  /** "" is the house drafter; a number is one of the court's own. */
  const [voiceId, setVoiceId] = useState<number | "">("");

  const generate = useCallback(
    async (asVoice: number | "" = voiceId) => {
      setBusy(true);
      setError(null);
      try {
        const result =
          asVoice === ""
            ? await load()
            : await api.suggestInCharacter(asVoice, hint);
        setText(result.body);
        setBackend("backend" in result ? result.backend : null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "לא הצלחנו לנסח כרגע.");
      } finally {
        setBusy(false);
      }
    },
    [load, hint, voiceId],
  );

  // Generate as the dialog opens; a closed dialog holds no stale draft.
  useEffect(() => {
    if (!open) {
      setText("");
      setBackend(null);
      setError(null);
      setVoiceId("");
      return;
    }
    void generate("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // The roster is only needed once the dialog is actually open, and only when
  // this composer offers voices at all.
  useEffect(() => {
    if (!open || !inCharacter || voiceCache) return;
    let cancelled = false;
    void api
      .fetchAgents()
      .then((roster) => {
        voiceCache = roster;
        if (!cancelled) setVoices(roster);
      })
      .catch(() => {
        // No roster means no picker. The house drafter still works.
      });
    return () => {
      cancelled = true;
    };
  }, [open, inCharacter]);

  const chooseVoice = (next: number | "") => {
    setVoiceId(next);
    void generate(next);
  };

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

        {inCharacter && voices.length > 0 && (
          <TextField
            select
            size="small"
            fullWidth
            label="מי מנסח"
            value={voiceId}
            onChange={(e) => chooseVoice(e.target.value === "" ? "" : Number(e.target.value))}
            disabled={busy}
            sx={{ mb: 1 }}
            inputProps={{ "data-testid": "assist-voice" }}
          >
            <MenuItem value="">מנסח בית המשפט</MenuItem>
            {(["judge", "juror", "moderator"] as const).flatMap((role) => {
              const members = voices.filter((voice) => voice.role === role);
              if (members.length === 0) return [];
              return [
                <ListSubheader key={role}>{AGENT_ROLE_LABELS[role]}</ListSubheader>,
                ...members.map((voice) => (
                  <MenuItem key={voice.id} value={voice.id}>
                    {voice.personality_name}
                  </MenuItem>
                )),
              ];
            })}
          </TextField>
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
