import { useState, useEffect } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Container, Box, Typography, TextField, InputAdornment,
  Table, TableHead, TableBody, TableRow, TableCell, TableContainer, Paper,
  Stack, Avatar, Button, CircularProgress, Alert,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";

import { fetchUsers } from "../api";
import { getInitials } from "../utils/stringUtils";
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
      <Box sx={{ mb: 3, textAlign: "center" }}>
        <Typography variant="h3" component="h1" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 900, color: "primary.dark" }}>
          לוח התובעים
        </Typography>
        <Typography sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic" }}>
          רשימת כל מי שהביא תביעה לבית המשפט. חפש שם או אימייל.
        </Typography>
      </Box>

      <TextField
        fullWidth
        placeholder="חיפוש לפי שם או אימייל..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 3, backgroundColor: "background.paper" }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon color="primary" />
            </InputAdornment>
          ),
        }}
      />

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
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow sx={{ backgroundColor: "primary.main" }}>
                  <TableCell sx={{ color: "background.default", fontWeight: 700, fontSize: "1rem" }}>תובע</TableCell>
                  <TableCell align="center" sx={{ color: "background.default", fontWeight: 700 }}>תביעות</TableCell>
                  <TableCell align="center" sx={{ color: "background.default", fontWeight: 700 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id} hover>
                    <TableCell>
                      <Stack direction="row" spacing={1.5} alignItems="center">
                        <Avatar sx={{ bgcolor: "primary.main", color: "background.default", fontWeight: 700 }}>
                          {getInitials(u.name)}
                        </Avatar>
                        <Box>
                          <Typography sx={{ fontWeight: 600, color: "primary.dark" }}>{u.name}</Typography>
                          <Typography variant="caption" sx={{ color: "text.secondary" }}>{u.email}</Typography>
                        </Box>
                      </Stack>
                    </TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600, fontSize: "1.05rem" }}>{u.post_count}</TableCell>
                    <TableCell align="center">
                      <Button component={RouterLink} to={`/user-posts/${u.id}`} variant="contained" size="small" startIcon={<FolderOpenIcon />}>
                        ראה תיק
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {hasMore && (
            <Box sx={{ display: "flex", justifyContent: "center", pt: 3 }}>
              <Button variant="outlined" onClick={loadMore} disabled={loadingMore} startIcon={loadingMore ? <CircularProgress size={18} /> : null}>
                {loadingMore ? "טוען..." : "טען עוד"}
              </Button>
            </Box>
          )}
        </>
      )}
    </Container>
  );
};

export default Users;
