import { useEffect, useState } from "react";

import { Box, Button, Stack, Typography } from "@mui/material";

import PostCard from "../post-card/PostCard";
import type { Post } from "../../types";

type UserPostsProps = {
  userName: string;
  posts: Post[];
  pageSize?: number;
};

const UserPosts = ({ userName, posts, pageSize = 5 }: UserPostsProps) => {
  const [visibleCount, setVisibleCount] = useState(pageSize);

  useEffect(() => {
    setVisibleCount(pageSize);
  }, [pageSize, posts]);

  const visiblePosts = posts.slice(0, visibleCount);

  if (posts.length === 0) {
    return (
      <Typography sx={{ textAlign: "center", color: "text.secondary", py: 6 }}>
        {userName} עדיין לא הגיש תביעות.
      </Typography>
    );
  }

  return (
    <Stack spacing={2}>
      {visiblePosts.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}

      {visibleCount < posts.length && (
        <Box sx={{ display: "flex", justifyContent: "center", pt: 1 }}>
          <Button variant="outlined" onClick={() => setVisibleCount((current) => current + pageSize)}>
            טען עוד
          </Button>
        </Box>
      )}
    </Stack>
  );
};

export default UserPosts;