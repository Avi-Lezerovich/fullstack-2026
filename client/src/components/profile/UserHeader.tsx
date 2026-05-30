import { Box, Paper, Stack, Avatar, Typography } from "@mui/material";

import { getInitials } from "../../utils/stringUtils";
import { formatHebrewDate } from "../../utils/dateUtils";
import type { User } from "../../types";

type UserHeaderProps = {
  user: User;
  postCount: number;
};

const UserHeader = ({ user, postCount }: UserHeaderProps) => {
  return (
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
            הצטרף ב-{formatHebrewDate(user.created_at)} · {postCount} תביעות
          </Typography>
        </Box>
      </Stack>
    </Paper>
  );
};
export default UserHeader;
    