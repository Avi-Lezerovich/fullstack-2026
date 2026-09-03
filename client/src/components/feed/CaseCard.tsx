import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import FavoriteIcon from "@mui/icons-material/Favorite";
import { Link as RouterLink } from "react-router-dom";

import CaseStatusChip from "../case/CaseStatusChip";
import CourtSeal from "../case/CourtSeal";
import FollowButton from "../case/FollowButton";
import { DOC_FONT } from "../../theme";
import type { Case } from "../../types";
import { initials, relativeTime } from "../../utils/format";

const PREVIEW_LENGTH = 220;

interface Props {
  case: Case;
  /** The personal feed sorts on activity, so it says what the activity was. */
  showActivity?: boolean;
  canFollow?: boolean;
}

const CaseCard = ({ case: c, showActivity, canFollow }: Props) => {
  const preview =
    c.body.length > PREVIEW_LENGTH ? `${c.body.slice(0, PREVIEW_LENGTH).trimEnd()}…` : c.body;

  return (
    // `position: relative` and `overflow: hidden` are for the seal: it is
    // stamped across the card rather than laid out beside anything, and the
    // rotation would otherwise poke past the rounded corner. See CourtSeal.tsx.
    <Card data-testid="case-card" sx={{ mb: 2, position: "relative", overflow: "hidden" }}>
      <CourtSeal status={c.status} />
      <CardActionArea component={RouterLink} to={`/cases/${c.id}`}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="flex-start">
            <Avatar src={c.author.avatar_url ?? undefined} sx={{ width: 40, height: 40 }}>
              {initials(c.author.name)}
            </Avatar>

            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
                <Typography variant="subtitle2" fontWeight={700}>
                  {c.author.name}
                </Typography>
                {c.author.is_bot && (
                  <SmartToyIcon fontSize="inherit" color="disabled" titleAccess="חשבון בוט" />
                )}
                <Typography variant="caption" color="text.secondary">
                  · הגיש/ה {relativeTime(c.filed_at)}
                </Typography>
              </Stack>

              <Typography variant="caption" color="text.secondary" display="block">
                נגד <strong>{c.defendant_text}</strong>
              </Typography>
            </Box>

            <CaseStatusChip status={c.status} deadline={c.phase_deadline_at} />
          </Stack>

          <Typography variant="h6" sx={{ mt: 1.5, lineHeight: 1.3 }}>
            {c.title}
          </Typography>

          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.5, fontFamily: DOC_FONT, whiteSpace: "pre-wrap" }}
          >
            {preview}
          </Typography>

          {c.charges.length > 0 && (
            <Stack direction="row" spacing={0.75} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
              {c.charges.map((charge) => (
                <Chip key={charge} label={charge} size="small" variant="outlined" />
              ))}
            </Stack>
          )}

          <Stack direction="row" spacing={2} sx={{ mt: 1.5 }} color="text.secondary">
            <Stack direction="row" spacing={0.5} alignItems="center">
              <FavoriteIcon fontSize="small" color={c.viewer_has_liked ? "error" : "inherit"} />
              <Typography variant="caption">{c.like_count}</Typography>
            </Stack>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <ChatBubbleOutlineIcon fontSize="small" />
              <Typography variant="caption">{c.comment_count}</Typography>
            </Stack>
            {showActivity && c.last_activity_at && (
              <Typography variant="caption">
                פעילות אחרונה {relativeTime(c.last_activity_at)}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </CardActionArea>

      {/* Outside the CardActionArea on purpose: it is a button, and nesting it
          inside the link would make every tap navigate as well as toggle. */}
      {canFollow && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", px: 2, pb: 1 }}>
          <FollowButton caseId={c.id} following={c.viewer_is_following} />
        </Box>
      )}
    </Card>
  );
}; export default CaseCard;
