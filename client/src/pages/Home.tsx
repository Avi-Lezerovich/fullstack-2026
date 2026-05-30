import { useState, useEffect } from "react";
import { Container, Stack, Box, Typography, Button, CircularProgress, Alert } from "@mui/material";

import PostCard from "../components/PostCard";
import { fetchPosts } from "../api";
import type { Post } from "../types";

/** How many posts to load per page (initial load and each "load more"). */
const PAGE_SIZE = 10;

/**
 * Home feed — route `/`.
 * Fetches the first 10 posts on mount, then appends 10 more each time the user
 * clicks "טען עוד" (Load More). A spinner shows while a request is in flight.
 */
const Home = () => {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");

  // Initial load of the first page.
  useEffect(() => {
    fetchPosts({ limit: PAGE_SIZE, offset: 0 })
      .then((data) => {
        setPosts(data);
        setHasMore(data.length === PAGE_SIZE);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "שגיאה בטעינת התביעות"))
      .finally(() => setLoading(false));
  }, []);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const next = await fetchPosts({ limit: PAGE_SIZE, offset: posts.length });
      setPosts((prev) => [...prev, ...next]);
      setHasMore(next.length === PAGE_SIZE);
    } catch (err) {
      setError(err instanceof Error ? err.message : "שגיאה בטעינת התביעות");
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Box sx={{ mb: 3, textAlign: "center" }}>
        <Typography variant="h3" component="h1" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 900, color: "primary.dark" }}>
          בית המשפט פתוח
        </Typography>
        <Typography sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic" }}>
          כל התביעות האחרונות שהוגשו לבית המשפט.
        </Typography>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : posts.length === 0 ? (
        <Typography sx={{ textAlign: "center", color: "text.secondary", py: 6 }}>
          אין תביעות להצגה.
        </Typography>
      ) : (
        <Stack spacing={2}>
          {posts.map((post) => (
            <PostCard key={post.id} post={post} />
          ))}

          {hasMore && (
            <Box sx={{ display: "flex", justifyContent: "center", pt: 2 }}>
              <Button
                variant="outlined"
                size="large"
                onClick={loadMore}
                disabled={loadingMore}
                startIcon={loadingMore ? <CircularProgress size={18} /> : null}
              >
                {loadingMore ? "טוען..." : "טען עוד תביעות"}
              </Button>
            </Box>
          )}
        </Stack>
      )}
    </Container>
  );
};

export default Home;
