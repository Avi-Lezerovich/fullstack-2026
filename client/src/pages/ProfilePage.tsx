import { useState, useEffect } from "react";
import { useParams, Link as RouterLink } from "react-router-dom";
import {
  Container, Box, Paper, Stack, Avatar, Typography, Button, Alert, CircularProgress,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import PostCard from "../components/PostCard";
import { fetchUserProfile } from "../api";
import { getInitials } from "../utils/stringUtils";
import { formatHebrewDate } from "../utils/dateUtils";
import type { Post, User } from "../types";

/** How many of the user's posts to reveal per "load more" click. */
const PAGE_SIZE = 5;

/**
 * Profile / user-posts page — route `/user-posts/:userId`.
 * Loads the user and all their posts, then reveals them in pages of 5 on the client.
 */
const ProfilePage = () => {
  const { userId } = useParams<{ userId: string }>();

  const [user, setUser] = useState<User | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = Number(userId);
    setLoading(true);
    fetchUserProfile(id)
      .then((data) => {
        setUser(data.user);
        setPosts(data.posts);
        setVisibleCount(PAGE_SIZE);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "התובע לא נמצא"))
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !user) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Alert severity="error">{error || "התובע לא נמצא"}</Alert>
        <Button component={RouterLink} to="/users" sx={{ mt: 2 }} startIcon={<ArrowBackIcon sx={{ transform: "scaleX(-1)" }} />}>
          חזרה ללוח התובעים
        </Button>
      </Container>
    );
  }

  const visiblePosts = posts.slice(0, visibleCount);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Button component={RouterLink} to="/users" sx={{ mb: 2 }} startIcon={<ArrowBackIcon sx={{ transform: "scaleX(-1)" }} />}>
        כל התובעים
      </Button>

      {/* Profile header */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Stack direction="row" spacing={2} alignItems="center">
          <Avatar sx={{ width: 64, height: 64, bgcolor: "primary.main", color: "background.default", fontWeight: 700, fontSize: "1.5rem" }}>
            {getInitials(user.name)}
          </Avatar>
          <Box>
            <Typography variant="h5" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, color: "primary.dark" }}>
              {user.name}
            </Typography>
            <Typography sx={{ color: "text.secondary" }}>{user.email}</Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              הצטרף ב-{formatHebrewDate(user.created_at)} · {posts.length} תביעות
            </Typography>
          </Box>
        </Stack>
      </Paper>

      <Typography variant="h5" sx={{ mb: 2, fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700 }}>
        תיק תביעות {user.name}
      </Typography>

      {posts.length === 0 ? (
        <Typography sx={{ textAlign: "center", color: "text.secondary", py: 6 }}>
          {user.name} עדיין לא הגיש תביעות.
        </Typography>
      ) : (
        <Stack spacing={2}>
          {visiblePosts.map((post) => (
            <PostCard key={post.id} post={post} />
          ))}

          {visibleCount < posts.length && (
            <Box sx={{ display: "flex", justifyContent: "center", pt: 1 }}>
              <Button variant="outlined" onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>
                טען עוד
              </Button>
            </Box>
          )}
        </Stack>
      )}
    </Container>
  );
};

export default ProfilePage;
