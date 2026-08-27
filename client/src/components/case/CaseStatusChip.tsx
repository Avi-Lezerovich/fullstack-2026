import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import GavelIcon from "@mui/icons-material/Gavel";
import GroupsIcon from "@mui/icons-material/Groups";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import LockIcon from "@mui/icons-material/Lock";
import DescriptionIcon from "@mui/icons-material/Description";

import { CASE_STATUS_LABELS, type CaseStatus } from "../../types";
import { timeUntil, isPast} from "../../utils/format";

type ChipColor = "default" | "info" | "secondary" | "success" | "primary";

/** How each phase presents itself: colour, icon, and what it means. */
const PRESENTATION: Record<CaseStatus, { color: ChipColor; icon: JSX.Element; hint: string }> = {
  filed: { color: "default", icon: <DescriptionIcon />, hint: "התביעה נקלטה." },
  witness_phase: {
    color: "info",
    icon: <RecordVoiceOverIcon />,
    hint: "הצדדים רשאים לזמן עדים.",
  },
  jury_deliberation: {
    color: "secondary",
    icon: <GroupsIcon />,
    hint: "שבעה מושבעים דנים בתיק ומצביעים.",
  },
  verdict_reached: { color: "primary", icon: <GavelIcon />, hint: "השופט נתן את פסק הדין." },
  closed: { color: "default", icon: <LockIcon />, hint: "התיק נסגר. אפשר עדיין להגיב ולסמן לייק." },
};

interface Props {
  status: CaseStatus;
  /** When the current phase ends; adds a countdown to the tooltip. */
  deadline?: string | null;
}

const CaseStatusChip = ({ status, deadline }: Props) => {
  const { color, icon, hint } = PRESENTATION[status];
  const remaining = status !== "closed" && !isPast(deadline ?? null) ? timeUntil(deadline ?? null) : "";


  return (
    <Tooltip title={remaining ? `${hint} השלב מסתיים ${remaining}.` : hint}>
      <Chip
        icon={icon}
        label={CASE_STATUS_LABELS[status]}
        color={color}
        size="small"
        variant={status === "closed" ? "outlined" : "filled"}
        data-testid="case-status-chip"
        data-status={status}
      />
    </Tooltip>
  );
}; export default CaseStatusChip;
