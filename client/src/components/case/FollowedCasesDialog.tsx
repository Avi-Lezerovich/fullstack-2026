import { useCallback } from "react";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../../api";
import InfiniteScroll from "../common/InfiniteScroll";
import { EmptyState, ErrorNote, Loading } from "../common/StateViews";
import { usePagedList } from "../../hooks/usePagedList";
import type { Case } from "../../types";
import { relativeTime } from "../../utils/format";

const PAGE_SIZE = 20;

interface Props {
  open: boolean;
  userId: number;
  /** Shown in the title, so it reads as somebody's list rather than a list. */
  name: string;
  onClose: () => void;
}

/**
 * The cases a person tracks — the list behind a profile's "tracking N cases".
 *
 * Cases rather than people, so this is not `UserListDialog`; it is paged
 * rather than capped, because a heavy user follows far more cases than a
 * filing collects likers, and `usePagedList` + the scroll sentinel already do
 * exactly that job for the feed.
 *
 * `open` is in the hook's deps so the list is fetched when the dialog opens
 * and refetched from the top the next time - a profile stays mounted while the
 * reader wanders off and comes back.
 */
const FollowedCasesDialog = ({ open, userId, name, onClose }: Props) => {
  const loadPage = useCallback(
    async (offset: number, limit: number) => {
      if (!open) return { items: [] as Case[], total: 0 };
      const page = await api.fetchUserFollows(userId, { limit, offset });
      return { items: page.cases, total: page.total };
    },
    [open, userId],
  );

  const { items, error, loading, hasMore, loadMore } = usePagedList(
    loadPage,
    [open, userId],
    PAGE_SIZE,
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      data-testid="followed-cases-dialog"
    >
      <DialogTitle>התיקים ש{name} עוקב/ת אחריהם</DialogTitle>
      <DialogContent sx={{ px: 1, pb: 2 }}>
        {error && <ErrorNote message={error} />}
        {loading && items.length === 0 && <Loading />}
        {!loading && items.length === 0 && !error && (
          <EmptyState title="לא עוקב/ת עדיין אחרי אף תיק" />
        )}

        {items.map((c) => (
          <ListItemButton
            key={c.id}
            component={RouterLink}
            to={`/cases/${c.id}`}
            onClick={onClose}
            data-testid="followed-case-row"
          >
            <Stack sx={{ width: "100%", minWidth: 0 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" fontWeight={700} sx={{ flex: 1 }} noWrap>
                  {c.title}
                </Typography>
                <Chip label={c.follow_count} size="small" variant="outlined" />
              </Stack>
              <Typography variant="caption" color="text.secondary" noWrap>
                נגד {c.defendant_text} · הוגש {relativeTime(c.filed_at)}
              </Typography>
            </Stack>
          </ListItemButton>
        ))}

        <InfiniteScroll hasMore={hasMore} loading={loading} onLoadMore={loadMore} />
      </DialogContent>
    </Dialog>
  );
}; export default FollowedCasesDialog;
