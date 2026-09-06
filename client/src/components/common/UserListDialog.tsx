import { useEffect, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { Link as RouterLink } from "react-router-dom";

import { EmptyState, ErrorNote, Loading } from "./StateViews";
import type { UserRef } from "../../types";
import { initials } from "../../utils/format";

interface Props {
  open: boolean;
  title: string;
  /** Shown when the list comes back empty. */
  emptyTitle: string;
  /** Called on open. Identity does not matter: the effect keys on `open`. */
  load: () => Promise<UserRef[]>;
  onClose: () => void;
  testId: string;
  rowTestId: string;
}

/**
 * A dialog listing people, behind a number.
 *
 * Two numbers on a case open one of these — who liked it, who tracks it — and
 * they differ only in their title and which endpoint they call, so the list
 * itself lives here rather than twice.
 *
 * Loads on open rather than with the page: most readers never ask who is
 * behind a count, and the case page already makes three requests before this
 * one. Closing throws the rows away, so reopening shows a current list rather
 * than whatever was true the first time.
 */
const UserListDialog = ({
  open,
  title,
  emptyTitle,
  load,
  onClose,
  testId,
  rowTestId,
}: Props) => {
  const [users, setUsers] = useState<UserRef[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setUsers(null);
      setError(null);
      return;
    }
    let cancelled = false;
    void load()
      .then((list) => {
        if (!cancelled) setUsers(list);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "לא הצלחנו לטעון את הרשימה.");
        }
      });
    return () => {
      cancelled = true;
    };
    // `load` is rebuilt on every render of the parent; keying on it would
    // refetch forever. `open` and the parent's own props are what change the
    // answer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" data-testid={testId}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ px: 1, pb: 2 }}>
        {error && <ErrorNote message={error} />}
        {!users && !error && <Loading />}
        {users?.length === 0 && <EmptyState title={emptyTitle} />}

        {users?.map((user) => (
          <ListItemButton
            key={user.id}
            component={RouterLink}
            to={`/users/${user.id}`}
            onClick={onClose}
            data-testid={rowTestId}
          >
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%" }}>
              <Avatar src={user.avatar_url ?? undefined} sx={{ width: 32, height: 32 }}>
                {initials(user.name)}
              </Avatar>
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
                {user.name}
              </Typography>
              {user.is_bot && <SmartToyIcon fontSize="small" color="disabled" />}
            </Stack>
          </ListItemButton>
        ))}
      </DialogContent>
    </Dialog>
  );
}; export default UserListDialog;
