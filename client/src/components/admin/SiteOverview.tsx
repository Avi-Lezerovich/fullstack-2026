import { useCallback } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import RefreshIcon from "@mui/icons-material/Refresh";

import * as api from "../../api";
import { ErrorNote, Loading } from "../common/StateViews";
import { useAsync } from "../../hooks/useAsync";

const TILES: { key: keyof api.SiteOverview; label: string }[] = [
  { key: "total_users", label: "משתמשים פעילים" },
  { key: "open_cases", label: "תיקים פתוחים" },
  { key: "pending_reports", label: "דיווחים ממתינים" },
  { key: "banned_users", label: "משתמשים מושעים" },
];

/**
 * The four numbers an admin opening the dashboard cold would ask for first.
 * Every one of them is a count the rest of the dashboard already keeps
 * somewhere - this just puts them side by side.
 */
const SiteOverview = () => {
  const load = useCallback(() => api.fetchSiteOverview(), []);
  const { data, error, loading, reload } = useAsync(load, []);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorNote message={error ?? "לא ניתן לטעון את סקירת האתר."} />;

  return (
    <Box data-testid="site-overview">
      <Stack direction="row" alignItems="center" justifyContent="flex-end" sx={{ mb: 1 }}>
        <IconButton size="small" onClick={() => reload()} aria-label="רענן" data-testid="refresh-overview">
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
        {TILES.map((tile) => (
          <Paper
            key={tile.key}
            variant="outlined"
            sx={{ p: 2, textAlign: "center", minWidth: 160, flex: "1 1 160px" }}
            data-testid={`overview-${tile.key}`}
          >
            <Typography variant="h4">{data[tile.key].toLocaleString("he-IL")}</Typography>
            <Typography variant="caption" color="text.secondary">
              {tile.label}
            </Typography>
          </Paper>
        ))}
      </Stack>
    </Box>
  );
};

export default SiteOverview;
