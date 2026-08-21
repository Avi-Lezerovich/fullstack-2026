import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import GavelIcon from "@mui/icons-material/Gavel";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";

import { VERDICT_LABELS, type JuryPanel as Panel } from "../../types";
import { initials, relativeTime } from "../../utils/format";

/**
 * The seven seats and the presiding judge.
 *
 * Seats are drawn in order because seat order IS speaking order — the panel
 * reads top to bottom as the deliberation unfolds. A juror who has not spoken
 * shows an hourglass rather than a blank, so a half-finished deliberation
 * looks deliberate rather than broken.
 */
const JuryPanel = ({ panel }: { panel: Panel }) => {
  const spoken = panel.members.filter((member) => member.vote !== null).length;
  const complete = spoken === panel.members.length;

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }} data-testid="jury-panel">
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        flexWrap="wrap"
        useFlexGap
        sx={{ mb: 1 }}
      >
        <Typography variant="h6">הרכב המושבעים</Typography>
        <Typography variant="caption" color="text.secondary" data-testid="jury-progress">
          {spoken} מתוך {panel.members.length} מושבעים הביעו את עמדתם
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
        <Avatar sx={{ bgcolor: "primary.main" }}>
          <GavelIcon fontSize="small" />
        </Avatar>
        <Box>
          <Typography variant="subtitle2" fontWeight={700}>
            {panel.judge.name}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            שופט/ת התיק
          </Typography>
        </Box>
      </Stack>

      <Divider sx={{ mb: 1.5 }} />

      <Stack spacing={1}>
        {panel.members.map((member) => {
          const waiting = member.vote === null;
          return (
            <Stack
              key={member.seat}
              direction="row"
              spacing={1.5}
              alignItems="center"
              data-testid="juror-seat"
              data-seat={member.seat}
              data-spoken={!waiting}
              sx={{ opacity: waiting ? 0.55 : 1 }}
            >
              <Avatar sx={{ width: 32, height: 32, fontSize: "0.8rem" }}>
                {initials(member.juror.name)}
              </Avatar>

              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} noWrap>
                  {member.juror.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  מושבע/ת {member.seat + 1}
                  {waiting
                    ? ` · צפוי/ה לדבר ${relativeTime(member.speaks_at)}`
                    : ` · דיבר/ה ${relativeTime(member.spoke_at)}`}
                </Typography>
              </Box>

              {waiting ? (
                <Tooltip title="טרם הביע/ה עמדה">
                  <HourglassEmptyIcon fontSize="small" color="disabled" />
                </Tooltip>
              ) : (
                <Chip
                  size="small"
                  label={VERDICT_LABELS[member.vote!]}
                  color={member.vote === "guilty" ? "error" : "success"}
                  variant="outlined"
                  data-testid="juror-vote"
                />
              )}
            </Stack>
          );
        })}
      </Stack>

      {complete && panel.tally_guilty !== null && (
        <>
          <Divider sx={{ my: 1.5 }} />
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" data-testid="jury-tally">
              תוצאת ההצבעה: {panel.tally_guilty} חייב · {panel.tally_not_guilty} זכאי
            </Typography>
            {panel.tiebreak_used && (
              <Chip size="small" color="warning" label="הוכרע בקול השופט/ת" />
            )}
          </Stack>
        </>
      )}
    </Paper>
  );
}; export default JuryPanel;
