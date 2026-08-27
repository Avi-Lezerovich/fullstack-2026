import { useCallback } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import * as api from "../../api";
import { useAsync } from "../../hooks/useAsync";

/**
 * Is the court actually running?
 *
 * The worker is a separate container, so "are trials advancing?" is not
 * otherwise visible from inside the app — a stalled scheduler looks exactly
 * like a quiet week. `/api/health` has always reported the tick count and the
 * age of the last tick; until now only Docker and curl read it.
 *
 * The staleness threshold matches the worker's own healthcheck in
 * docker-compose.yml, so the badge here and the container's status agree.
 */
const STALE_AFTER_SECONDS = 120;

const CourtStatus = () => {
  const load = useCallback(() => api.fetchHealth(), []);
  const { data, error } = useAsync(load, []);

  if (error || !data) return null;

  const worker = data.worker;
  const since = worker?.seconds_since_tick ?? null;
  const ticking = since !== null && since < STALE_AFTER_SECONDS;

  const workerLabel = !worker
    ? "המתזמן מעולם לא רץ"
    : ticking
      ? `המתזמן פעיל · ${worker.tick_count.toLocaleString("he-IL")} סבבים`
      : "המתזמן אינו מגיב";

  return (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }} data-testid="court-status">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="caption" color="text.secondary" sx={{ me: 1 }}>
          מצב המערכת
        </Typography>

        <Chip
          size="small"
          color={data.database === "up" ? "success" : "error"}
          variant="outlined"
          label={data.database === "up" ? "מסד הנתונים מחובר" : "מסד הנתונים מנותק"}
          data-testid="health-db"
        />

        <Tooltip
          title={
            worker?.last_tick_at
              ? `הסבב האחרון: ${worker.last_tick_at}`
              : "אין רישום של סבב שהושלם"
          }
        >
          <Chip
            size="small"
            color={ticking ? "success" : "warning"}
            variant="outlined"
            label={workerLabel}
            data-testid="health-worker"
            data-ticking={ticking}
          />
        </Tooltip>

        <Chip
          size="small"
          variant="outlined"
          label={data.brain === "llm" ? "מנוע: בינה מלאכותית" : "מנוע: מקומי"}
        />
        <Chip
          size="small"
          variant="outlined"
          label={`${data.phase_minutes} דקות לשלב`}
        />

        {worker?.last_error && (
          <Box sx={{ width: "100%" }}>
            <Typography variant="caption" color="error" data-testid="health-error">
              שגיאת מתזמן אחרונה: {worker.last_error}
            </Typography>
          </Box>
        )}
      </Stack>
    </Paper>
  );
}; export default CourtStatus;
