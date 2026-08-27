import { useCallback, useEffect, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../api";
import { EmptyState, ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";
import { initials } from "../utils/format";

/** The server caps a page at fifty, so this is as large as one request gets. */
const PAGE_SIZE = 50;

const Users = () => {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [limit, setLimit] = useState(PAGE_SIZE);

  // Typing should not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // A new search starts from the top; keeping the grown page size would ask
  // for five hundred strangers the moment somebody types a letter.
  useEffect(() => {
    setLimit(PAGE_SIZE);
  }, [debounced]);

  /**
   * Pages are accumulated by asking for more rows from the start rather than
   * by walking `offset`. The list is ordered by name, so a page boundary is
   * stable, and this keeps the rendered list a single consistent snapshot.
   */
  const load = useCallback(
    async () => {
      const pages = Math.ceil(limit / PAGE_SIZE);
      const responses = await Promise.all(
        Array.from({ length: pages }, (_, index) =>
          api.fetchUsers({ search: debounced, limit: PAGE_SIZE, offset: index * PAGE_SIZE }),
        ),
      );
      return {
        users: responses.flatMap((response) => response.users),
        total: responses[responses.length - 1].total,
      };
    },
    [debounced, limit],
  );
  const { data, error, loading } = useAsync(load, [debounced, limit]);
  const users = data?.users ?? [];
  const hasMore = data ? users.length < data.total : false;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        אנשי החצר
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        תובעים, נתבעים, ותשעה-עשר פקידי בית משפט שאף פעם לא הולכים הביתה.
      </Typography>

      <TextField
        label="חיפוש לפי שם"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
        sx={{ mb: 2 }}
        inputProps={{ "data-testid": "user-search" }}
      />

      {error && <ErrorNote message={error} />}
      {loading && users.length === 0 && <Loading />}
      {!loading && users.length === 0 && !error && <EmptyState title="לא נמצאו משתמשים" />}

      <Stack spacing={1}>
        {users.map((user) => (
          <Card key={user.id} data-testid="user-row">
            <CardActionArea component={RouterLink} to={`/users/${user.id}`} sx={{ p: 1.5 }}>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Avatar src={user.avatar_url ?? undefined}>{initials(user.name)}</Avatar>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Stack direction="row" spacing={0.75} alignItems="center">
                    <Typography fontWeight={700} noWrap>
                      {user.name}
                    </Typography>
                    {user.is_admin && <Chip label="מנהל" size="small" color="primary" />}
                  </Stack>
                  {user.bio && (
                    <Typography variant="caption" color="text.secondary" noWrap display="block">
                      {user.bio}
                    </Typography>
                  )}
                </Box>
                {user.is_bot && (
                  <Chip icon={<SmartToyIcon />} label="בוט" size="small" variant="outlined" />
                )}
              </Stack>
            </CardActionArea>
          </Card>
        ))}
      </Stack>

      {hasMore && (
        <Box sx={{ textAlign: "center", mt: 2 }}>
          <Button onClick={() => setLimit((n) => n + PAGE_SIZE)} disabled={loading}>
            {loading ? "טוען…" : "טען עוד"}
          </Button>
        </Box>
      )}
    </Box>
  );
}; export default Users;
