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

import * as api from "../../api";
import { EmptyState, ErrorNote, Loading } from "../common/StateViews";
import type { UserRef } from "../../types";
import { initials } from "../../utils/format";

interface Props {
  open: boolean;
  caseId: number;
  onClose: () => void;
}

/**
 * The list behind a like count.
 *
 * Loads on open rather than with the page: most readers never ask who liked a
 * filing, and the case page already makes three requests before this one.
 */
const LikersDialog = ({ open, caseId, onClose }: Props) => {
  const [users, setUsers] = useState<UserRef[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setUsers(null);
      setError(null);
      return;
    }
    let cancelled = false;
    void api
      .fetchLikers(caseId)
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
  }, [open, caseId]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" data-testid="likers-dialog">
      <DialogTitle>מי אהב את התביעה</DialogTitle>
      <DialogContent sx={{ px: 1, pb: 2 }}>
        {error && <ErrorNote message={error} />}
        {!users && !error && <Loading />}
        {users?.length === 0 && <EmptyState title="עוד אף אחד" />}

        {users?.map((user) => (
          <ListItemButton
            key={user.id}
            component={RouterLink}
            to={`/users/${user.id}`}
            onClick={onClose}
            data-testid="liker-row"
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
}; export default LikersDialog;
