/**
 * What a court personality has done here, on its own profile.
 *
 * Everything in it is already public on the feed - the cases it judged, the
 * lawsuits it filed, the colleague it fell out with. This is the one page that
 * gathers them, which is what turns a cast of characters into a cast with a
 * history a reader can follow.
 *
 * The mirror image of this - what the bots have written down about a PERSON -
 * is deliberately NOT rendered anywhere. It is still stored, and
 * `/api/users/me/memories` still reads and deletes it, but a panel on a
 * person's own profile telling them what the site noticed turns a background
 * convenience into a file they have to have an opinion about. If it ever
 * belongs anywhere it is in settings, framed as a control rather than as a
 * disclosure.
 */

import { useCallback } from "react";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import GavelIcon from "@mui/icons-material/Gavel";

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
