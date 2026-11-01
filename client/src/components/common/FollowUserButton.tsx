import { useEffect, useRef, useState } from "react";
import Button from "@mui/material/Button";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import PersonRemoveIcon from "@mui/icons-material/PersonRemove";

import * as api from "../../api";

interface Props {
  userId: number;
  following: boolean;
  /** Told the server's answer, so the profile can redraw its follower count. */
  onChange?: (next: { following: boolean; follower_count: number }) => void;
}

/**
 * Follow a person - their filings then show up in "My Feed".
 *
 * The person-shaped sibling of the case FollowButton, with the same rules: the
 * server returns the authoritative state, and a failed toggle leaves the
 * previous one visible rather than flipping optimistically.
 */
const FollowUserButton = ({ userId, following, onChange }: Props) => {
  const [state, setState] = useState(following);
  const [busy, setBusy] = useState(false);

  // Adopt new props only when they actually change; see FollowButton.
  const lastProp = useRef(following);
  useEffect(() => {
    if (lastProp.current === following) return;
    lastProp.current = following;
    setState(following);
  }, [following]);

  const toggle = async () => {
    setBusy(true);
    try {
      const next = await api.toggleFollowUser(userId);
      setState(next.following);
      onChange?.(next);
    } catch {
      // Keep the previous state; it is still the true one.
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      variant={state ? "outlined" : "contained"}
      onClick={toggle}
      disabled={busy}
      startIcon={state ? <PersonRemoveIcon /> : <PersonAddIcon />}
      data-testid="follow-user-button"
      data-following={state}
    >
      {state ? "עוקב/ת" : "עקוב/עקבי"}
    </Button>
  );
}; export default FollowUserButton;
