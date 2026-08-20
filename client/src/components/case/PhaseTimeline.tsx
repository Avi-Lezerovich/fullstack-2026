import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Typography from "@mui/material/Typography";

import { type CaseStatus } from "../../types";
import { timeUntil, isPast} from "../../utils/format";

/** `filed` is never observed in practice, so it is folded into the first step. */
const STEPS: { status: CaseStatus; label: string }[] = [
  { status: "witness_phase", label: "איסוף עדויות" },
  { status: "jury_deliberation", label: "דיוני מושבעים" },
  { status: "verdict_reached", label: "פסק דין" },
  { status: "closed", label: "התיק נסגר" },
];

interface Props {
  status: CaseStatus;
  deadline: string | null;
}

const PhaseTimeline = ({ status, deadline }: Props) => {
  const index = Math.max(
    0,
    STEPS.findIndex((step) => step.status === (status === "filed" ? "witness_phase" : status)),
  );
  const finished = status === "closed";

  return (
    <Box data-testid="phase-timeline" data-status={status}>
      <Stepper activeStep={index} alternativeLabel sx={{ mb: 1 }}>
        {STEPS.map((step) => (
          <Step key={step.status} completed={finished || STEPS.indexOf(step) < index}>
            <StepLabel>{step.label}</StepLabel>
          </Step>
        ))}
      </Stepper>

    {!finished && deadline && (
    <Stack direction="row" justifyContent="center">
        <Typography variant="caption" color="text.secondary">
        {isPast(deadline) ? "השלב הנוכחי הסתיים" : `השלב הנוכחי מסתיים ${timeUntil(deadline)}`}
        </Typography>
    </Stack>
    )}
    </Box>
  );
};  export default PhaseTimeline;
