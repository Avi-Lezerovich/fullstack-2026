import { useState } from "react";
import Button from "@mui/material/Button";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";

import AssistDialog from "./AssistDialog";

interface Props {
  label: string;
  title: string;
  helper?: string;
  load: () => Promise<{ body: string; backend: string }>;
  onAccept: (text: string) => void;
  acceptLabel?: string;
  size?: "small" | "medium";
  disabled?: boolean;
  /** Offer the nineteen court personalities as authors. */
  inCharacter?: boolean;
  /** Seeds an in-character draft so it is about this case, not any case. */
  hint?: string;
}

/**
 * The trigger and its dialog in one drop-in unit, so a composer only has to
 * say what it wants written and where the result goes.
 */
const AssistButton = ({ label, size = "medium", disabled, ...dialog }: Props) => {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        size={size}
        startIcon={<AutoAwesomeIcon />}
        onClick={() => setOpen(true)}
        disabled={disabled}
        data-testid="assist-button"
      >
        {label}
      </Button>
      <AssistDialog open={open} onClose={() => setOpen(false)} {...dialog} />
    </>
  );
}; export default AssistButton;
