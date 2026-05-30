import { useState } from "react";
import { Box, Paper, Stack, Avatar, Typography, Button, CircularProgress } from "@mui/material";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import PersonRemoveIcon from "@mui/icons-material/PersonRemove";
import EditIcon from "@mui/icons-material/Edit";

import EditProfileDialog from "./EditProfileDialog";
import { followUser, unfollowUser } from "../../api";
import { getInitials } from "../../utils/stringUtils";
import { formatHebrewDate } from "../../utils/dateUtils";
import type { User } from "../../types";

type UserHeaderProps = {
  user: User;
  postCount: number;
  followersCount: number;
  followingCount: number;
  isFollowing: boolean;
  /** True when the logged-in user is viewing their own profile. */
  isSelf: boolean;
  /** True when someone is logged in (controls whether the Follow button shows). */
  isAuthed: boolean;
  onProfileUpdated: (user: User) => void;
};

/** A labelled count, e.g. "12 עוקבים". */
const Stat = ({ value, label }: { value: number; label: string }) => (
  <Box sx={{ textAlign: "center" }}>
    <Typography component="span" sx={{ fontWeight: 700 }}>{value}</Typography>{" "}
    <Typography component="span" variant="body2" sx={{ color: "text.secondary" }}>{label}</Typography>
  </Box>
);

const UserHeader = ({
  user, postCount, followersCount, followingCount, isFollowing, isSelf, isAuthed, onProfileUpdated,
}: UserHeaderProps) => {
  const [following, setFollowing] = useState(isFollowing);
  const [followers, setFollowers] = useState(followersCount);
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const toggleFollow = async () => {
    setBusy(true);
    try {
      if (following) {
        await unfollowUser(user.id);
        setFollowing(false);
        setFollowers((c) => Math.max(0, c - 1));
      } else {
        await followUser(user.id);
        setFollowing(true);
        setFollowers((c) => c + 1);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper sx={{ p: 3, mb: 3 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ xs: "flex-start", sm: "center" }}>
        <Avatar
          src={user.avatar_url || undefined}
          sx={{ width: 80, height: 80, bgcolor: "primary.main", color: "background.default", fontWeight: 700, fontSize: "1.75rem" }}
        >
          {getInitials(user.name)}
        </Avatar>

        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, color: "primary.dark" }}>
            {user.name}
          </Typography>
          <Typography sx={{ color: "text.secondary" }}>{user.email}</Typography>
          {user.bio && <Typography sx={{ mt: 1, color: "text.primary" }}>{user.bio}</Typography>}
          <Typography variant="caption" sx={{ display: "block", mt: 1, color: "text.secondary" }}>
            הצטרף ב-{formatHebrewDate(user.created_at)}
          </Typography>

          <Stack direction="row" spacing={3} sx={{ mt: 1.5 }}>
            <Stat value={postCount} label="תביעות" />
            <Stat value={followers} label="עוקבים" />
            <Stat value={followingCount} label="עוקב" />
          </Stack>
        </Box>

        {isSelf ? (
          <Button variant="outlined" startIcon={<EditIcon />} onClick={() => setEditOpen(true)}>
            עריכת פרופיל
          </Button>
        ) : isAuthed ? (
          <Button
            variant={following ? "outlined" : "contained"}
            color={following ? "inherit" : "secondary"}
            disabled={busy}
            onClick={toggleFollow}
            startIcon={busy ? <CircularProgress size={16} /> : following ? <PersonRemoveIcon /> : <PersonAddIcon />}
          >
            {following ? "הפסק לעקוב" : "עקוב"}
          </Button>
        ) : null}
      </Stack>

      {isSelf && (
        <EditProfileDialog
          open={editOpen}
          user={user}
          onClose={() => setEditOpen(false)}
          onSaved={onProfileUpdated}
        />
      )}
    </Paper>
  );
};

export default UserHeader;
