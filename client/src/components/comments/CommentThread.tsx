import { useState } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { Link as RouterLink } from "react-router-dom";

import CommentComposer from "./CommentComposer";
import RoleBadge from "./RoleBadge";
import ReportButton from "../moderation/ReportButton";
import { DOC_FONT } from "../../theme";
import type { Comment } from "../../types";
import { initials, relativeTime } from "../../utils/format";

/** Indentation per nesting level. Depth is capped server-side at 3. */
const INDENT_PX = 28;

interface Props {
  comments: Comment[];
  canReply: boolean;
  onReply: (body: string, parentId: number) => Promise<void>;
}

const CommentItem = ({
  comment,
  canReply,
  onReply,
}: {
  comment: Comment;
  canReply: boolean;
  onReply: (body: string, parentId: number) => Promise<void>;
}) => {
  const [replying, setReplying] = useState(false);
  const isBot = comment.author.is_bot;

  return (
    <Box
      sx={{ marginInlineStart: `${comment.depth * INDENT_PX}px` }}
      data-testid="comment-item"
      data-role={comment.role}
      data-depth={comment.depth}
    >
      <Paper
        variant="outlined"
        sx={{
          p: 1.5,
          mb: 1,
          // Trial content is the court speaking, so it gets a tinted card to
          // separate it from the public's comments.
          bgcolor: comment.role === "user" ? "background.paper" : "rgba(60, 52, 137, 0.04)",
          borderInlineStartWidth: comment.role === "user" ? 1 : 3,
          borderInlineStartColor: comment.role === "user" ? "divider" : "secondary.main",
        }}
      >
        <Stack direction="row" spacing={1.5} alignItems="flex-start">
          <Avatar
            src={comment.author.avatar_url ?? undefined}
            sx={{ width: 32, height: 32 }}
            component={RouterLink}
            to={`/users/${comment.author.id}`}
          >
            {initials(comment.author.name)}
          </Avatar>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="subtitle2" fontWeight={700}>
                {comment.author.name}
              </Typography>
              {isBot && <SmartToyIcon fontSize="inherit" color="disabled" titleAccess="בוט" />}
              <RoleBadge role={comment.role} />
              <Typography variant="caption" color="text.secondary">
                {relativeTime(comment.created_at)}
              </Typography>
            </Stack>

            {comment.is_hidden && comment.body === null ? (
              <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                <VisibilityOffIcon fontSize="small" color="disabled" />
                <Typography variant="body2" color="text.disabled" fontStyle="italic">
                  התוכן הוסר על ידי הפיקוח.
                </Typography>
              </Stack>
            ) : (
              <Typography
                variant="body2"
                sx={{ mt: 0.5, whiteSpace: "pre-wrap", fontFamily: DOC_FONT }}
              >
                {comment.body}
              </Typography>
            )}

            {canReply && !comment.is_hidden && (
              <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                <Button size="small" onClick={() => setReplying((open) => !open)}>
                  {replying ? "ביטול" : "השב"}
                </Button>
                {/* Court speech is not reportable — the bots are the venue,
                    not participants in it. */}
                {comment.role === "user" && (
                  <ReportButton targetType="comment" targetId={comment.id} />
                )}
              </Stack>
            )}
          </Box>
        </Stack>

        {replying && (
          <Box sx={{ mt: 1 }}>
            <CommentComposer
              placeholder="תשובה…"
              submitLabel="שלח תשובה"
              onSubmit={async (body) => {
                await onReply(body, comment.id);
                setReplying(false);
              }}
            />
          </Box>
        )}
      </Paper>
    </Box>
  );
}

const CommentThread = ({ comments, canReply, onReply }: Props) => {
  if (comments.length === 0) {
    return (
      <Typography color="text.secondary" sx={{ py: 2 }} data-testid="comments-empty">
        עוד לא נאמר דבר בתיק הזה.
      </Typography>
    );
  }

  return (
    <Box data-testid="comment-thread">
      {comments.map((comment) => (
        <CommentItem
          key={comment.id}
          comment={comment}
          canReply={canReply}
          onReply={onReply}
        />
      ))}
    </Box>
  );
}; export default CommentThread;
