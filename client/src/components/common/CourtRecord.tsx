/**
 * A court personality's own record, and the file the court keeps on you.
 *
 * Two panels, one component, because they are two halves of the same question
 * - "what does this site remember" - answered from opposite sides:
 *
 *   CourtRecord   what a BOT has done here. Public, because every entry in it
 *                 is already on the feed; this is just the one page that
 *                 gathers them.
 *   MyMemories    what the bots have WRITTEN DOWN about you. Private to you,
 *                 and deletable, because a memory its subject cannot read is a
 *                 file the site keeps on them. The server has had both
 *                 endpoints since the memory layer shipped and nothing on the
 *                 client ever called them - which meant the deletion existed
 *                 only for whoever knew how to use curl.
 */

import { useCallback, useState } from "react";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import GavelIcon from "@mui/icons-material/Gavel";
import PsychologyIcon from "@mui/icons-material/Psychology";

import * as api from "../../api";
import { RECORD_KIND_LABELS } from "../../types";
import { useAsync } from "../../hooks/useAsync";
import { ErrorNote, Loading } from "./StateViews";
import { formatDate } from "../../utils/format";

export const CourtRecord = ({ userId }: { userId: number }) => {
  const load = useCallback(() => api.fetchCourtRecord(userId), [userId]);
  const record = useAsync(load, [userId]);

  if (record.loading) return <Loading />;
  if (record.error) return <ErrorNote message={record.error} />;
  // Silent rather than an empty state: a freshly seeded bot genuinely has no
  // history yet, and an empty panel saying so on every profile is noise.
  if (!record.data?.length) return null;

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <GavelIcon fontSize="small" color="action" />
        <Typography variant="h6">מה עשית כאן</Typography>
      </Stack>

      <Stack divider={<Divider flexItem />} spacing={1.25}>
        {record.data.map((entry, index) => (
          <Stack
            key={`${entry.created_at}-${index}`}
            direction="row"
            spacing={1.5}
            alignItems="flex-start"
            sx={{ pt: index === 0 ? 0 : 1.25 }}
          >
            <Chip
              label={RECORD_KIND_LABELS[entry.kind] ?? entry.kind}
              size="small"
              variant="outlined"
              sx={{ flexShrink: 0 }}
            />
            <Stack sx={{ minWidth: 0 }}>
              <Typography variant="body2">{entry.summary}</Typography>
              {entry.created_at && (
                <Typography variant="caption" color="text.secondary">
                  {formatDate(entry.created_at)}
                </Typography>
              )}
            </Stack>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
};

export const MyMemories = () => {
  const load = useCallback(() => api.fetchMyMemories(), []);
  const memories = useAsync(load, []);
  const [forgetting, setForgetting] = useState(false);

  const forget = async () => {
    // No confirmation dialog. Deleting is the safe direction here - the bots
    // simply stop bringing up old conversations - and putting a speed bump in
    // front of "stop remembering me" would be the wrong instinct entirely.
    setForgetting(true);
    try {
      await api.forgetMe();
      await memories.reload();
    } finally {
      setForgetting(false);
    }
  };

  if (memories.loading) return <Loading />;
  if (memories.error) return <ErrorNote message={memories.error} />;

  const rows = memories.data ?? [];

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <PsychologyIcon fontSize="small" color="action" />
        <Typography variant="h6">מה בית המשפט זוכר עליך</Typography>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        כשאתה מתכתב עם אחת מדמויות בית המשפט, היא שומרת סיכום קצר של השיחה כדי
        שלא תצטרך להתחיל מהתחלה בכל פעם. זה כל מה שנשמר, וזה נמחק כאן.
      </Typography>

      {rows.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          אף דמות לא רשמה עליך כלום.
        </Typography>
      ) : (
        <Stack divider={<Divider flexItem />} spacing={1.5}>
          {rows.map((memory) => (
            <Stack key={memory.bot} spacing={0.5} sx={{ pt: 1 }}>
              <Typography variant="subtitle2">{memory.bot}</Typography>
              <Typography variant="body2">{memory.summary}</Typography>
              {memory.facts.length > 0 && (
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                  {memory.facts.map((fact) => (
                    <Chip key={fact} label={fact} size="small" variant="outlined" />
                  ))}
                </Stack>
              )}
              {memory.updated_at && (
                <Typography variant="caption" color="text.secondary">
                  עודכן {formatDate(memory.updated_at)}
                </Typography>
              )}
            </Stack>
          ))}
        </Stack>
      )}

      {rows.length > 0 && (
        <Button
          color="error"
          onClick={forget}
          disabled={forgetting}
          sx={{ mt: 2 }}
          data-testid="forget-me"
        >
          {forgetting ? "מוחק…" : "שכחו אותי"}
        </Button>
      )}
    </Paper>
  );
};
