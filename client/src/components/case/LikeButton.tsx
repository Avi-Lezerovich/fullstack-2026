import { useEffect, useRef, useState } from "react";
import Button from "@mui/material/Button";
import FavoriteIcon from "@mui/icons-material/Favorite";
import FavoriteBorderIcon from "@mui/icons-material/FavoriteBorder";

import * as api from "../../api";

interface Props {
  caseId: number;
  liked: boolean;
  count: number;
  disabled?: boolean;
  /** The feed card carries the number in its stat row, so the button there is
   *  the word alone and the count is not printed twice. Mirrors FollowButton. */
  showCount?: boolean;
  /** Told the server's answer, so a parent showing the same numbers elsewhere
   *  - the feed card's stat row - can redraw them without a refetch. */
  onChange?: (next: { liked: boolean; like_count: number }) => void;
}

const LikeButton = ({
  caseId,
  liked,
  count,
  disabled,
  showCount = true,
  onChange,
}: Props) => {
  const [state, setState] = useState({ liked, like_count: count });
  const [busy, setBusy] = useState(false);

  /**
   * Adopt the props only when the props themselves change.
   *
   * The case page refetches every ten seconds while a trial is live, so these
   * values move underneath us when somebody else — or a bot — likes the
   * filing, and `useState` reads its argument only on the first render. So a
   * sync is needed; the subtlety is when NOT to run it.
   *
   * Comparing against the last props we saw is what makes that safe. Keying
   * the effect on a `busy` flag instead looks equivalent and is not: `busy`
   * going false is itself a change, so the effect re-ran the instant our own
   * request finished and overwrote the server's fresh answer with the stale
   * props the parent had not refetched yet. The like landed in the database
   * and the button snapped straight back.
   */
  const lastProps = useRef({ liked, count });
  useEffect(() => {
    if (lastProps.current.liked === liked && lastProps.current.count === count) return;
    lastProps.current = { liked, count };
    setState({ liked, like_count: count });
  }, [liked, count]);

  const toggle = async () => {
    setBusy(true);
    try {
      // The server returns the authoritative state, so the button cannot drift
      // out of step by guessing what the new value should be.
      const next = await api.toggleLike(caseId);
      setState(next);
      // Safe to tell the parent, which will hand these straight back as props:
      // the guarded sync above compares against the last props it SAW, so it
      // adopts them once and stops.
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
      color={state.liked ? "error" : "inherit"}
      startIcon={state.liked ? <FavoriteIcon /> : <FavoriteBorderIcon />}
      data-testid="like-button"
      data-liked={state.liked}
      data-like-count={state.like_count}
    >
      {/* On the case page the number IS the label - it is the only place the
          like total appears there. On a feed card the stat row above already
          prints it, so the button says the word instead. */}
      {showCount ? state.like_count : state.liked ? "אהבתי" : "לייק"}
    </Button>
  );
}; export default LikeButton;
