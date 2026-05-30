import { Link as RouterLink } from "react-router-dom";
import { Avatar, Box, Stack,Typography} from "@mui/material";



import { formatRelative } from "../../utils/dateUtils";
import { getInitials } from "../../utils/stringUtils";
import { Post } from "../../types";





const AuthorHeader = ({ post }: { post: Post }) => {
  return (

        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
          <Avatar
            component={RouterLink}
            to={`/user-posts/${post.author_id}`}
            sx={{ bgcolor: "primary.main", color: "background.default", fontWeight: 700, textDecoration: "none" }}
          >
            {getInitials(post.author_name)}
          </Avatar>
          <Box>
            <Typography
              component={RouterLink}
              to={`/user-posts/${post.author_id}`}
              sx={{ fontWeight: 700, color: "primary.dark", textDecoration: "none" }}
            >
              {post.author_name}
            </Typography>
            <Typography variant="caption" sx={{ display: "block", color: "text.secondary" }}>
              {formatRelative(post.created_at)}
            </Typography>
          </Box>
        </Stack>
    );
};

export default AuthorHeader;