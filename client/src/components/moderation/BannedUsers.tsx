import { useCallback, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../../api";
import { EmptyState, ErrorNote, Loading } from "../common/StateViews";
import { useAsync } from "../../hooks/useAsync";
import { initials } from "../../utils/format";

/**
 * Suspended accounts, and the button that reinstates them.
 *
 * `/admin/users/:id/unban` has always existed, but a banned user is invisible
 * to `GET /users` — it only ever returns active accounts — so there was no way
 * to find anybody to point it at. `/admin/users/banned` closes that loop, and
 * makes a ban a decision rather than a one-way door.
 */
const BannedUsers = () => {
  const load = useCallback(() => api.fetchBannedUsers(), []);
  const { data, error, loading, reload } = useAsync(load, []);
  const [busy, setBusy] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const unban = async (userId: number) => {
    setBusy(userId);
    setFailure(null);
    try {
      await api.unbanUser(userId);
      await reload();
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "לא הצלחנו לבטל את ההשעיה.");
    } finally {
      setBusy(null);
    }
  };

  const users = data ?? [];

  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        חשבונות מושעים. השעיה מנתקת את כל המכשירים המחוברים, אבל אינה מוחקת דבר — ביטול
        ההשעיה מחזיר את החשבון לפעילות מלאה.
      </Typography>

      {error && <ErrorNote message={error} />}
      {failure && <ErrorNote message={failure} />}
      {loading && !data && <Loading />}
      {!loading && users.length === 0 && !error && (
        <EmptyState title="אין חשבונות מושעים" description="בית המשפט שקט." />
      )}

      <Stack spacing={1}>
        {users.map((user) => (
          <Paper key={user.id} variant="outlined" sx={{ p: 1.5 }} data-testid="banned-row">
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar src={user.avatar_url ?? undefined}>{initials(user.name)}</Avatar>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box
                  component={RouterLink}
                  to={`/users/${user.id}`}
                  sx={{ color: "primary.main", fontWeight: 700, textDecoration: "none" }}
                >
                  {user.name}
                </Box>
                {user.bio && (
                  <Typography variant="caption" color="text.secondary" noWrap display="block">
                    {user.bio}
                  </Typography>
                )}
              </Box>
              <Button
                size="small"
                variant="contained"
                disabled={busy === user.id}
                onClick={() => unban(user.id)}
                data-testid="unban-button"
              >
                {busy === user.id ? "מבטל…" : "בטל השעיה"}
              </Button>
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}; export default BannedUsers;
