import { useState, useEffect } from "react";
import { useParams, Link as RouterLink } from "react-router-dom";
import {
  Container, Box, Typography, Button, Alert, CircularProgress,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import UserHeader from "../components/profile/UserHeader";
import UserPosts from "../components/profile/UserPosts";
import { fetchUserProfile } from "../api";
import type { Post, User } from "../types";

/**
 * Profile / user-posts page — route `/user-posts/:userId`.
 * Loads the user and all their posts, then reveals them in pages of 5 on the client.
 */
const ProfilePage = () => {
  const { userId } = useParams<{ userId: string }>();

  const [user, setUser] = useState<User | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = Number(userId);
    setLoading(true);
    fetchUserProfile(id)
      .then((data) => {
        setUser(data.user);
        setPosts(data.posts);
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

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Button component={RouterLink} to="/users" sx={{ mb: 2 }} startIcon={<ArrowBackIcon sx={{ transform: "scaleX(-1)" }} />}>
        כל התובעים
      </Button>

      <UserHeader user={user} postCount={posts.length} />

      <Typography variant="h5" sx={{ mb: 2, fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700 }}>
        תיק תביעות {user.name}
      </Typography>

      <UserPosts userName={user.name} posts={posts} />
    </Container>
  );
};

export default ProfilePage;
