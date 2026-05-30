import { Box, Button, CircularProgress, Stack } from "@mui/material";

import PostCard from "../post-card/PostCard";
import type { Post } from "../../types";

type PostListProps = {
  posts: Post[];
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
};

const PostList = ({ posts, hasMore, loadingMore, onLoadMore }: PostListProps) => (
  <Stack spacing={2}>
    {posts.map((post) => (
      <PostCard key={post.id} post={post} />
    ))}

    {hasMore && (
      <Box sx={{ display: "flex", justifyContent: "center", pt: 2 }}>
        <Button
          variant="outlined"
          size="large"
          onClick={onLoadMore}
          disabled={loadingMore}
          startIcon={loadingMore ? <CircularProgress size={18} /> : null}
        >
          {loadingMore ? "טוען..." : "טען עוד תביעות"}
        </Button>
      </Box>
    )}
  </Stack>
);

export default PostList;
