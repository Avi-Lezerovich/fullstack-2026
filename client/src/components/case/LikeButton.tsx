import { useState } from "react";
import Button from "@mui/material/Button";
import FavoriteIcon from "@mui/icons-material/Favorite";
import FavoriteBorderIcon from "@mui/icons-material/FavoriteBorder";

import * as api from "../../api";

interface Props {
  caseId: number;
  liked: boolean;
  count: number;
  disabled?: boolean;
  onChange?: (state: { liked: boolean; like_count: number }) => void;
}

const LikeButton = ({ caseId, liked, count, disabled, onChange }: Props) => {
  const [state, setState] = useState({ liked, like_count: count });
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    setBusy(true);
    try {
      // The server returns the authoritative state, so the button cannot drift
      // out of step by guessing what the new value should be.
      const next = await api.toggleLike(caseId);
      setState(next);
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
    >
      {state.like_count}
    </Button>
  );
}; export default LikeButton;
