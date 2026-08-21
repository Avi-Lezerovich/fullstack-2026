import Chip from "@mui/material/Chip";
import GavelIcon from "@mui/icons-material/Gavel";
import GroupsIcon from "@mui/icons-material/Groups";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";

import { COMMENT_ROLE_LABELS, type CommentRole } from "../../types";

type BadgeColor = "info" | "secondary" | "primary";

/**
 * Marks what kind of utterance a comment is. Plain user comments get no badge
 * at all — they are the default, and labelling them would be noise.
 */
const PRESENTATION: Partial<Record<CommentRole, { color: BadgeColor; icon: JSX.Element }>> = {
  witness_testimony: { color: "info", icon: <RecordVoiceOverIcon /> },
  jury_deliberation: { color: "secondary", icon: <GroupsIcon /> },
  verdict: { color: "primary", icon: <GavelIcon /> },
};

const RoleBadge = ({ role }: { role: CommentRole }) => {
  const presentation = PRESENTATION[role];
  if (!presentation) return null;

  return (
    <Chip
      size="small"
      icon={presentation.icon}
      color={presentation.color}
      label={COMMENT_ROLE_LABELS[role]}
      data-testid="role-badge"
      data-role={role}
    />
  );
}; export default RoleBadge;
