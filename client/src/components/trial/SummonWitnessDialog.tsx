import { useEffect, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";

import * as api from "../../api";
import { ErrorNote } from "../common/StateViews";
import type { User } from "../../types";

interface Props {
  open: boolean;
  caseId: number;
  remaining: number;
  onClose: () => void;
  onSummoned: () => void;
}

const SummonWitnessDialog = ({
  open,
  caseId,
  remaining,
  onClose,
  onSummoned,
}: Props) => {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<User[]>([]);
  const [chosen, setChosen] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // include_bots=0: the court personalities are not eligible
  // witnesses, so they are never even offered.
  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setOptions([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const { users } = await api.fetchUsers({ search: query, limit: 8, include_bots: false });
        if (!cancelled) setOptions(users);
      } catch {
        if (!cancelled) setOptions([]);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, query]);

  const submit = async () => {
    if (!chosen) return;
    setError(null);
    setBusy(true);
    try {
      await api.summonWitness(caseId, chosen.id);
      setChosen(null);
      setQuery("");
      onSummoned();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "לא הצלחנו לזמן את העד.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>זימון עד</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          אפשר לזמן עד {remaining} עדים נוספים. עדים חייבים להיות משתמשים אנושיים שאינם צד לתיק.
        </DialogContentText>

        {error && <ErrorNote message={error} />}

        <Autocomplete
          options={options}
          value={chosen}
          onChange={(_, value) => setChosen(value)}
          onInputChange={(_, text) => setQuery(text)}
          getOptionLabel={(option) => option.name}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          noOptionsText={query.length < 2 ? "הקלד לפחות שתי אותיות" : "לא נמצאו משתמשים"}
          renderInput={(params) => (
            <TextField {...params} label="חיפוש עד" autoFocus data-testid="summon-search" />
          )}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>ביטול</Button>
        <Button
          onClick={submit}
          variant="contained"
          disabled={!chosen || busy}
          data-testid="summon-submit"
        >
          {busy ? "מזמן…" : "זמן לעדות"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}; export default SummonWitnessDialog;
