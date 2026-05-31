import { useState, useEffect } from "react";
import { useParams, Link as RouterLink } from "react-router-dom";
import {
  Container, Box, Typography, Button, Alert, CircularProgress,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import UserHeader from "../components/profile/UserHeader";
import UserPosts from "../components/profile/UserPosts";
import { fetchUserProfile, getStoredUser, saveSession } from "../api";
import { useCurrentUser } from "../hooks/useCurrentUser";
import type { Post, User, UserProfileResponse } from "../types";

/**
 * Profile / user-posts page — route `/user-posts/:userId`.
 * Loads the user, their posts and follow stats. Shows a Follow/Unfollow button
 * (for others) or an edit-profile affordance (for your own page).
 */
const ProfilePage = () => {
  const { userId } = useParams<{ userId: string }>();
  const currentUser = useCurrentUser();

  const [profile, setProfile] = useState<UserProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = Number(userId);
    setLoading(true);
    fetchUserProfile(id)
      .then((data) => {
        setProfile(data);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "התובע לא נמצא"))
      .finally(() => setLoading(false));
  }, [userId]);

  // After editing your own profile, update the page and the cached session user.
  const handleProfileUpdated = (updated: User) => {
    setProfile((prev) => (prev ? { ...prev, user: updated } : prev));
    if (getStoredUser()?.id === updated.id) saveSession(updated);
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !profile) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Alert severity="error">{error || "התובע לא נמצא"}</Alert>
        <Button component={RouterLink} to="/users" sx={{ mt: 2 }} startIcon={<ArrowBackIcon sx={{ transform: "scaleX(-1)" }} />}>
          חזרה ללוח התובעים
        </Button>
      </Container>
    );
  }

  const { user, posts } = profile;
  const isSelf = currentUser?.id === user.id;

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Button component={RouterLink} to="/users" sx={{ mb: 2 }} startIcon={<ArrowBackIcon sx={{ transform: "scaleX(-1)" }} />}>
        כל התובעים
      </Button>

      <UserHeader
        user={user}
        postCount={posts.length}
        followersCount={profile.followers_count}
        followingCount={profile.following_count}
        isFollowing={profile.is_following}
        isSelf={!!isSelf}
        isAuthed={!!currentUser}
        onProfileUpdated={handleProfileUpdated}
      />

      <Typography variant="h5" sx={{ mb: 2, fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700 }}>
        תיק תביעות {user.name}
      </Typography>

      <UserPosts userName={user.name} posts={posts as Post[]} />
    </Container>
  );
};

export default ProfilePage;
