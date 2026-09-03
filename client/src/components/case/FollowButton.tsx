import { useEffect, useRef, useState } from "react";
import Button from "@mui/material/Button";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";

import * as api from "../../api";

interface Props {
  caseId: number;
  following: boolean;
  disabled?: boolean;
}

const FollowButton = ({ caseId, following, disabled }: Props) => {
  const [state, setState] = useState(following);
  const [busy, setBusy] = useState(false);

  // Same guarded prop-sync as LikeButton, for the same reason: the case page
  // refetches every ten seconds while a trial is live, and a naive effect
  // would overwrite the server's fresh answer with props the parent has not
  // refetched yet. Comparing against the last props we saw is what makes it
  // safe. See LikeButton.tsx for the long version.
  const lastProp = useRef(following);
  useEffect(() => {
    if (lastProp.current === following) return;
    lastProp.current = following;
    setState(following);
  }, [following]);

  const toggle = async () => {
    setBusy(true);
    try {
      const next = await api.toggleFollow(caseId);
      setState(next.following);
    } catch {
      // Leaving the previous state visible is the honest outcome of a failed
      // toggle; an optimistic flip here would claim something untrue.
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button
      onClick={toggle}
      disabled={disabled || busy}
      color={state ? "primary" : "inherit"}
      startIcon={state ? <BookmarkIcon /> : <BookmarkBorderIcon />}
      data-testid="follow-button"
      data-following={state}
    >
      {state ? "עוקב" : "עקוב"}
    </Button>
  );
}; export default FollowButton;
