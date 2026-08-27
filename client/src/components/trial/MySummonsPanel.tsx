import { useCallback } from "react";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../../api";
import { useAsync } from "../../hooks/useAsync";
import { relativeTime } from "../../utils/format";

/**
 * "You have been summoned" — shown at the top of the feed.
 *
 * A summons used to be announced only by a bell notification. Miss it and the
 * witness phase closes without you, the summons is marked `no_show`, and the
 * first you hear of it is a second notification telling you that you failed to
 * appear. `GET /me/summons` has always been able to answer "which cases are
 * waiting on me"; nothing was asking.
 *
 * It lives on the feed rather than behind its own route because the feed is
 * where people land, and a page nobody visits would not have fixed anything.
 * Renders nothing when there is nothing outstanding.
 */
const MySummonsPanel = () => {
  const load = useCallback(() => api.fetchMySummons(), []);
  const { data, error } = useAsync(load, []);

  // Silent on failure: a broken side-panel must not shout over the feed.
  if (error || !data || data.length === 0) return null;

  return (
    <Alert
      severity="info"
      icon={<RecordVoiceOverIcon fontSize="inherit" />}
      variant="outlined"
      sx={{ mb: 2, borderWidth: 2 }}
      data-testid="my-summons"
    >
      <AlertTitle sx={{ fontWeight: 700 }}>
        {data.length === 1 ? "זומנת למסור עדות" : `זומנת למסור עדות ב-${data.length} תיקים`}
      </AlertTitle>

      <Stack spacing={1} sx={{ mt: 0.5 }}>
        {data.map((summons) => (
          <Stack
            key={summons.id}
            direction={{ xs: "column", sm: "row" }}
            spacing={{ xs: 0.5, sm: 1.5 }}
            alignItems={{ xs: "flex-start", sm: "center" }}
            data-testid="my-summons-row"
          >
            <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
              <strong>{summons.case_title}</strong>
              {summons.deadline_at && (
                <Typography component="span" variant="caption" color="text.secondary">
                  {" "}
                  · שלב איסוף העדויות מסתיים {relativeTime(summons.deadline_at)}
                </Typography>
              )}
            </Typography>
            <Button
              size="small"
              variant="contained"
              component={RouterLink}
              to={`/cases/${summons.case_id}`}
              data-testid="my-summons-link"
            >
              מסור עדות
            </Button>
          </Stack>
        ))}
      </Stack>
    </Alert>
  );
}; export default MySummonsPanel;
