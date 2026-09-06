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
import BookmarkIcon from "@mui/icons-material/Bookmark";
import { Link as RouterLink } from "react-router-dom";

import CaseStatusChip from "../case/CaseStatusChip";
import CourtSeal from "../case/CourtSeal";
import FollowButton from "../case/FollowButton";
import LikeButton from "../case/LikeButton";
import { DOC_FONT } from "../../theme";
import type { Case } from "../../types";
import { initials, relativeTime } from "../../utils/format";

const PREVIEW_LENGTH = 220;

interface Props {
  case: Case;
  /** The personal feed sorts on activity, so it says what the activity was. */
  showActivity?: boolean;
  /** Signed in: the card gets its action row. Signed out it is counts only. */
  canFollow?: boolean;
  /**
   * The viewer liked or followed from here. The card's stat row reads the
   * `case` prop, so without a way to say so the numbers under the buttons kept
   * the values the feed was fetched with until the page was reloaded - a like
   * that visibly did nothing. The list owns the row, so the list applies it.
   */
  onChange?: (patch: Partial<Case>) => void;
}

const CaseCard = ({ case: c, showActivity, canFollow, onChange }: Props) => {
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

          {/* The evidence, if any was filed.
              A card is a fixed-width thing in a scrolling column, so the image
              is given a fixed height and told to cover it: a phone photo three
              times taller than it is wide would otherwise push the charges, the
              counts and the next card entirely off the screen, and a column of
              cards whose heights depend on what people photographed reads as
              broken layout rather than as variety. Cropping loses part of the
              picture — the case page shows it whole, uncropped, which is where
              a reader who cares about the evidence is going anyway.

              Nothing here is directional. This renders under stylis-plugin-rtl,
              which mirrors physical offsets (see CourtSeal.tsx for what that
              did to a centred `left: 50%`); `mt` is block-axis and untouched by
              it, and `objectPosition` is left at its centred default rather
              than named, so there is no left/right for the mirror to flip. */}
          {c.image_url && (
            <Box
              component="img"
              src={c.image_url}
              alt=""
              // Same as the case page: a dead link must leave nothing behind.
              // A broken-image glyph in the middle of the feed looks like the
              // site is broken, not like one upload expired.
              onError={(event) => {
                (event.currentTarget as HTMLImageElement).style.display = "none";
              }}
              sx={{
                display: "block",
                width: "100%",
                height: { xs: 180, sm: 220 },
                objectFit: "cover",
                borderRadius: 1,
                border: "1px solid",
                borderColor: "divider",
                mt: 1.5,
              }}
              data-testid="card-image"
            />
          )}

          {c.charges.length > 0 && (
            <Stack direction="row" spacing={0.75} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
              {c.charges.map((charge) => (
                <Chip key={charge} label={charge} size="small" variant="outlined" />
              ))}
            </Stack>
          )}

          <Stack direction="row" spacing={2} sx={{ mt: 1.5 }} color="text.secondary">
            <Stack direction="row" spacing={0.5} alignItems="center" data-testid="card-like-count">
              <FavoriteIcon fontSize="small" color={c.viewer_has_liked ? "error" : "inherit"} />
              <Typography variant="caption">{c.like_count}</Typography>
            </Stack>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <ChatBubbleOutlineIcon fontSize="small" />
              <Typography variant="caption">{c.comment_count}</Typography>
            </Stack>
            {/* Public, so it is here signed out too - where there is no follow
                button to carry it. */}
            <Stack
              direction="row"
              spacing={0.5}
              alignItems="center"
              data-testid="card-follow-count"
            >
              <BookmarkIcon fontSize="small" color={c.viewer_is_following ? "primary" : "inherit"} />
              <Typography variant="caption">{c.follow_count}</Typography>
            </Stack>
            {showActivity && c.last_activity_at && (
              <Typography variant="caption">
                פעילות אחרונה {relativeTime(c.last_activity_at)}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </CardActionArea>

      {/* Outside the CardActionArea on purpose: these are buttons, and nesting
          them inside the link would make every tap navigate as well as toggle.
          The counts they change are printed in the stat row above, which is
          why neither button repeats one. */}
      {canFollow && (
        <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end", px: 2, pb: 1 }}>
          <LikeButton
            caseId={c.id}
            liked={c.viewer_has_liked}
            count={c.like_count}
            showCount={false}
            onChange={({ liked, like_count }) =>
              onChange?.({ viewer_has_liked: liked, like_count })
            }
          />
          <FollowButton
            caseId={c.id}
            following={c.viewer_is_following}
            count={c.follow_count}
            showCount={false}
            onChange={({ following, follow_count }) =>
              onChange?.({ viewer_is_following: following, follow_count })
            }
          />
        </Stack>
      )}
    </Card>
  );
}; export default CaseCard;
