import { Link as RouterLink } from "react-router-dom";
import {
  Avatar, Box, Button, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Typography,
} from "@mui/material";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";

import { getInitials } from "../../utils/stringUtils";
import type { UserListItem } from "../../types";

type UsersTableProps = {
  users: UserListItem[];
};

const UsersTable = ({ users }: UsersTableProps) => (
  <TableContainer component={Paper}>
    <Table>
      <TableHead>
        <TableRow sx={{ backgroundColor: "primary.main" }}>
          <TableCell sx={{ color: "background.default", fontWeight: 700, fontSize: "1rem" }}>תובע</TableCell>
          <TableCell align="center" sx={{ color: "background.default", fontWeight: 700 }}>תביעות</TableCell>
          <TableCell align="center" sx={{ color: "background.default", fontWeight: 700 }} />
        </TableRow>
      </TableHead>
      <TableBody>
        {users.map((u) => (
          <TableRow key={u.id} hover>
            <TableCell>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Avatar sx={{ bgcolor: "primary.main", color: "background.default", fontWeight: 700 }}>
                  {getInitials(u.name)}
                </Avatar>
                <Box>
                  <Typography sx={{ fontWeight: 600, color: "primary.dark" }}>{u.name}</Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>{u.email}</Typography>
                </Box>
              </Stack>
            </TableCell>
            <TableCell align="center" sx={{ fontWeight: 600, fontSize: "1.05rem" }}>{u.post_count}</TableCell>
            <TableCell align="center">
              <Button component={RouterLink} to={`/user-posts/${u.id}`} variant="contained" size="small" startIcon={<FolderOpenIcon />}>
                ראה תיק
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
);

export default UsersTable;
