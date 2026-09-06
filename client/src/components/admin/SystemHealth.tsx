import { useCallback } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import RefreshIcon from "@mui/icons-material/Refresh";

import * as api from "../../api";
import { ErrorNote, Loading } from "../common/StateViews";
import { useAsync } from "../../hooks/useAsync";
import { hasBrainMismatch, isWorkerTicking } from "../../utils/adminOps";
import { relativeTime } from "../../utils/format";

const POLL_MS = 15000;

/**
 * DB, worker heartbeat and the brain's configured-vs-actual backend, polled
 * live so an admin watching a stalled worker does not have to keep hitting
 * refresh to see it recover.
 *
 * This is the same `/api/health` CourtStatus already reads - already public,
 * already exactly this shape - so there is no second, admin-gated endpoint
 * here. The one thing added on top is the mismatch banner: `data.brain` used
 * to be compared as a bare string ("llm"), which never matched the object the
 * server actually sends, so the badge above the queue has been silently wrong
 * since the day the shape changed. Fixed alongside this, since both read the
 * same field.
 */
const SystemHealth = () => {
  const load = useCallback(() => api.fetchHealth(), []);
  const { data, error, loading, reload } = useAsync(load, [], POLL_MS);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorNote message={error ?? "לא ניתן לטעון את מצב המערכת."} />;

  const worker = data.worker;
  const ticking = isWorkerTicking(worker?.seconds_since_tick ?? null);
  const mismatch = hasBrainMismatch(data.brain);

  return (
    <Box data-testid="system-health">
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography color="text.secondary">
          מסד הנתונים, המתזמן ומנוע הבינה המלאכותית, מתעדכן אוטומטית כל {POLL_MS / 1000} שניות.
        </Typography>
        <IconButton size="small" onClick={() => reload()} aria-label="רענן" data-testid="refresh-health">
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Stack>

      <Stack spacing={1.5}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            מסד נתונים
          </Typography>
          <Chip
            size="small"
            color={data.database === "up" ? "success" : "error"}
            label={data.database === "up" ? "מחובר" : "מנותק"}
            data-testid="health-db-chip"
          />
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            המתזמן (Worker)
          </Typography>
          {worker ? (
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Chip
                size="small"
                color={ticking ? "success" : "error"}
                label={ticking ? "פעיל" : "אינו מגיב"}
                data-testid="health-worker-chip"
              />
              <Typography variant="body2" color="text.secondary">
                {worker.tick_count.toLocaleString("he-IL")} סבבים · סבב אחרון{" "}
                {worker.last_tick_at ? relativeTime(worker.last_tick_at) : "מעולם לא"}
              </Typography>
            </Stack>
          ) : (
            <Chip size="small" color="error" label="המתזמן מעולם לא רץ" />
          )}
          {worker?.last_error && (
            <Typography variant="caption" color="error" display="block" sx={{ mt: 1 }}>
              שגיאה אחרונה: {worker.last_error}
            </Typography>
          )}
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            מנוע הבינה המלאכותית
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              size="small"
              variant="outlined"
              label={`הוגדר: ${data.brain.configured === "llm" ? "בינה מלאכותית" : "מקומי"}`}
            />
            <Chip
              size="small"
              variant="outlined"
              color={mismatch ? "warning" : "default"}
              label={`בפועל: ${
                data.brain.last_backend === "unknown"
                  ? "טרם בוצעה קריאה"
                  : data.brain.last_backend === "llm"
                    ? "בינה מלאכותית"
                    : "מקומי"
              }`}
              data-testid="health-brain-actual"
            />
          </Stack>

          {mismatch && (
            <Alert severity="warning" sx={{ mt: 1.5 }} data-testid="brain-mismatch-alert">
              התצורה אומרת "{data.brain.configured}", אך הקריאה האחרונה בפועל ענתה "
              {data.brain.last_backend}". המנוע מוגדר לעבוד מול בינה מלאכותית אך נופל בפועל
              למחולל המקומי - כנראה תקלת אימות או חבילה חסרה בקונטיינר.
              {data.brain.last_error && ` (${data.brain.last_error})`}
            </Alert>
          )}
        </Paper>
      </Stack>
    </Box>
  );
};

export default SystemHealth;
