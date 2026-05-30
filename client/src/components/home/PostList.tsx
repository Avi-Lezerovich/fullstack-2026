import { useEffect, useRef } from "react";
import { Box, Button, CircularProgress, Stack } from "@mui/material";

import PostCard from "../post-card/PostCard";
import type { Post } from "../../types";

type PostListProps = {
  posts: Post[];
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
};

/**
 * Renders the feed and drives infinite scroll: an IntersectionObserver watches a
 * sentinel near the bottom and auto-loads the next page as it scrolls into view.
 * The "טען עוד" button stays as an explicit fallback (and for non-observer cases).
 */
const PostList = ({ posts, hasMore, loadingMore, onLoadMore }: PostListProps) => {
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore) onLoadMore();
      },
      { rootMargin: "400px" }, // start loading before the user hits the very bottom
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

  return (
    <Stack spacing={2}>
      {posts.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}

      {hasMore && (
        // The whole footer is the auto-load sentinel (non-zero height so the
        // IntersectionObserver reliably fires); the button is a manual fallback.
        <Box ref={sentinelRef} sx={{ display: "flex", justifyContent: "center", pt: 2, minHeight: 48 }}>
          {loadingMore ? (
            <CircularProgress size={28} />
          ) : (
            <Button variant="outlined" size="large" onClick={onLoadMore}>
              טען עוד תביעות
            </Button>
          )}
        </Box>
      )}
    </Stack>
  );
};

export default PostList;
