import {
    Chip,
    Stack,
    Typography,
} from "@mui/material";

import GavelIcon from "@mui/icons-material/Gavel";

import { Post } from "../../types";

const PostTitle = ({ post }: { post: Post }) => {
    return (
        <>
            {/* Title */}
            <Typography
                variant="h5"
                component="h2"
                sx={{ fontFamily: '"Frank Ruhl Libre", serif', fontWeight: 700, color: "primary.dark", mb: 1 }}
            >
                {post.title}
            </Typography>

            {/* Parties line */}
            <Typography sx={{ color: "text.secondary", mb: 1.5 }}>
                <GavelIcon sx={{ fontSize: 18, verticalAlign: "text-bottom", color: "secondary.main", ml: 0.5 }} />
                הנתבע: <strong>{post.defendant}</strong>
            </Typography>

            {/* Charges */}
            {post.charges && post.charges.length > 0 && (
                <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: "wrap", gap: 1 }}>
                    {post.charges.map((charge) => (
                        <Chip key={charge} label={charge} size="small" color="secondary" variant="outlined" />
                    ))}
                </Stack>
            )}
        </>
    );
};
export default PostTitle;