import { useState, useEffect, useCallback } from "react";
import { Container, Box, Typography, CircularProgress, Alert, Tabs, Tab } from "@mui/material";

import HomeHeader from "../components/home/HomeHeader";
import PostList from "../components/home/PostList";
import { fetchPosts } from "../api";
import { useCurrentUser } from "../hooks/useCurrentUser";
import type { Post } from "../types";

/** How many posts to load per page (initial load and each "load more"). */
const PAGE_SIZE = 10;

type Feed = "global" | "following";

/**
 * Home feed — route `/`.
 * Two feeds via tabs: the global feed (all posts) and, when logged in, the
 * "following" feed (only people you follow). Posts load lazily as you scroll.
 */
const Home = () => {
  const user = useCurrentUser();
  const [feed, setFeed] = useState<Feed>("global");
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");

  // Reset to the global feed if the user logs out while on the following tab.
  useEffect(() => {
    if (!user && feed === "following") setFeed("global");
  }, [user, feed]);

  // (Re)load the first page whenever the active feed changes.
  useEffect(() => {
    setLoading(true);
    setError("");
    fetchPosts({ limit: PAGE_SIZE, offset: 0, feed })
      .then((data) => {
        setPosts(data);
        setHasMore(data.length === PAGE_SIZE);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "שגיאה בטעינת התביעות"))
      .finally(() => setLoading(false));
  }, [feed]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const next = await fetchPosts({ limit: PAGE_SIZE, offset: posts.length, feed });
      setPosts((prev) => [...prev, ...next]);
      setHasMore(next.length === PAGE_SIZE);
    } catch (err) {
      setError(err instanceof Error ? err.message : "שגיאה בטעינת התביעות");
    } finally {
      setLoadingMore(false);
    }
  }, [posts.length, feed]);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <HomeHeader />

      {user && (
        <Tabs
          value={feed}
          onChange={(_, v: Feed) => setFeed(v)}
          centered
          sx={{ mb: 3 }}
        >
          <Tab value="global" label="כל התביעות" />
          <Tab value="following" label="העוקבים שלי" />
        </Tabs>
      )}

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : posts.length === 0 ? (
        <Typography sx={{ textAlign: "center", color: "text.secondary", py: 6 }}>
          {feed === "following"
            ? "עדיין אין תביעות מחשבונות במעקב. מומלץ לעקוב אחר תובעים כדי למלא את הפיד."
            : "אין תביעות להצגה."}
        </Typography>
      ) : (
        <PostList posts={posts} hasMore={hasMore} loadingMore={loadingMore} onLoadMore={loadMore} />
      )}
    </Container>
  );
};

export default Home;
