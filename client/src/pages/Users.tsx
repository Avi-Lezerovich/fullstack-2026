import { useState, useEffect } from "react";
import {
  Container, Box, Typography, CircularProgress, Alert,
} from "@mui/material";

import UsersHeader from "../components/users/UsersHeader";
import UserSearchField from "../components/users/UserSearchField";
import UsersTable from "../components/users/UsersTable";
import LoadMoreButton from "../components/users/LoadMoreButton";
import { fetchUsers } from "../api";
import type { UserListItem } from "../types";

const PAGE_SIZE = 10;
const DEBOUNCE_MS = 300;

/**
 * Users directory — route `/users`.
 * A search box (debounced 300ms) filters by name/email; results render in a table.
 * "טען עוד" loads the next 10 users.
 */
const Users = () => {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");

  // Debounce the search box so we don't refetch on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  // Fetch the first page whenever the (debounced) search term changes.
  useEffect(() => {
    setLoading(true);
    fetchUsers({ search: debouncedSearch, limit: PAGE_SIZE, offset: 0 })
      .then((data) => {
        setUsers(data);
        setHasMore(data.length === PAGE_SIZE);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "שגיאה בטעינת התובעים"))
      .finally(() => setLoading(false));
  }, [debouncedSearch]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const next = await fetchUsers({ search: debouncedSearch, limit: PAGE_SIZE, offset: users.length });
      setUsers((prev) => [...prev, ...next]);
      setHasMore(next.length === PAGE_SIZE);
    } catch (err) {
      setError(err instanceof Error ? err.message : "שגיאה בטעינת התובעים");
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <UsersHeader />

      <UserSearchField value={search} onChange={(e) => setSearch(e.target.value)} />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : users.length === 0 ? (
        <Typography variant="h6" sx={{ textAlign: "center", color: "text.secondary", py: 6 }}>
          {debouncedSearch ? "אין תוצאות לחיפוש." : "אין תובעים רשומים."}
        </Typography>
      ) : (
        <>
          <UsersTable users={users} />
          {hasMore && <LoadMoreButton loadingMore={loadingMore} onLoadMore={loadMore} />}
        </>
      )}
    </Container>
  );
};

export default Users;
