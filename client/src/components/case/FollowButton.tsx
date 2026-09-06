import { useEffect, useRef, useState } from "react";
import Button from "@mui/material/Button";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";

import * as api from "../../api";

interface Props {
  caseId: number;
  following: boolean;
  count: number;
  disabled?: boolean;
  /** The feed card carries the number in its stat row, so the button there is
   *  the word alone and the count is not printed twice. */
  showCount?: boolean;
  /** Told the server's answer, so a parent showing the same numbers elsewhere
   *  - the feed card's stat row - can redraw them without a refetch. */
  onChange?: (next: { following: boolean; follow_count: number }) => void;
}

const FollowButton = ({
  caseId,
  following,
  count,
  disabled,
  showCount = true,
  onChange,
}: Props) => {
  const [state, setState] = useState({ following, follow_count: count });
  const [busy, setBusy] = useState(false);

  // Same guarded prop-sync as LikeButton, for the same reason: the case page
  // refetches every ten seconds while a trial is live, and a naive effect
  // would overwrite the server's fresh answer with props the parent has not
  // refetched yet. Comparing against the last props we saw is what makes it
  // safe. See LikeButton.tsx for the long version.
  const lastProps = useRef({ following, count });
  useEffect(() => {
    if (lastProps.current.following === following && lastProps.current.count === count) return;
    lastProps.current = { following, count };
    setState({ following, follow_count: count });
  }, [following, count]);

  const toggle = async () => {
    setBusy(true);
    try {
      // The server returns the authoritative state AND the new total, so the
      // count cannot drift by being incremented from a stale one.
      const next = await api.toggleFollow(caseId);
      setState(next);
      // Safe to tell the parent, which will hand these straight back as props:
      // the sync below compares against the last props it SAW, so it adopts
      // them once and stops. See LikeButton for why that guard is written that
      // way rather than around a `busy` flag.
      onChange?.(next);
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
      color={state.following ? "primary" : "inherit"}
      startIcon={state.following ? <BookmarkIcon /> : <BookmarkBorderIcon />}
      data-testid="follow-button"
      data-following={state.following}
      data-follow-count={state.follow_count}
    >
      {state.following ? "עוקב" : "עקוב"}
      {showCount && ` · ${state.follow_count}`}
    </Button>
  );
}; export default FollowButton;
