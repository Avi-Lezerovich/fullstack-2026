import { useCallback, useEffect, useState } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import PersonAddAlt1Icon from "@mui/icons-material/PersonAddAlt1";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";

import * as api from "../api";
import CaseStatusChip from "../components/case/CaseStatusChip";
import LikeButton from "../components/case/LikeButton";
import LikersDialog from "../components/case/LikersDialog";
import PhaseTimeline from "../components/case/PhaseTimeline";
import VerdictBanner from "../components/case/VerdictBanner";
import CommentComposer from "../components/comments/CommentComposer";
import CommentThread from "../components/comments/CommentThread";
import { ErrorNote, Loading } from "../components/common/StateViews";
import ReportButton from "../components/moderation/ReportButton";
import JuryPanel from "../components/trial/JuryPanel";
import SummonWitnessDialog from "../components/trial/SummonWitnessDialog";
import TestifyForm from "../components/trial/TestifyForm";
import WitnessList from "../components/trial/WitnessList";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../context/AuthContext";
import { DOC_FONT } from "../theme";
import { formatDate, initials, relativeTime } from "../utils/format";

/**
 * While a trial is live the server is changing the case underneath us — jurors
 * speak on their own schedule. Polling keeps the page honest without requiring
 * a refresh; it stops once the case is closed and nothing more can happen.
 */
const LIVE_REFRESH_MS = 10_000;

const CasePage = () => {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const id = Number(caseId);

  const { data: c, error, loading, reload: reloadCase } = useAsync(
    useCallback(() => api.fetchCase(id), [id]),
    [id],
  );
  const comments = useAsync(useCallback(() => api.fetchComments(id), [id]), [id]);
  const trial = useAsync(useCallback(() => api.fetchTrial(id), [id]), [id]);

  const [summonOpen, setSummonOpen] = useState(false);
  const [likersOpen, setLikersOpen] = useState(false);

  // All three reloads are `useCallback`s from useAsync, stable for as long as
  // their own deps are, so naming them here is honest rather than a lie the
  // linter had to be silenced about.
  const reloadComments = comments.reload;
  const reloadTrial = trial.reload;
  const reloadAll = useCallback(async () => {
    await Promise.all([reloadCase(), reloadComments(), reloadTrial()]);
  }, [reloadCase, reloadComments, reloadTrial]);

  const live = c ? c.status !== "closed" : false;
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => void reloadAll(), LIVE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [live, reloadAll]);

  const addComment = async (body: string, parentId?: number) => {
    await api.createComment(id, body, parentId ?? null);
    await comments.reload();
  };

  const withdraw = async () => {
    if (!window.confirm("למשוך את התביעה? הפעולה אינה הפיכה.")) return;
    try {
      await api.deleteCase(id);
      navigate("/");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "לא הצלחנו למשוך את התביעה.");
    }
  };

  if (loading && !c) return <Loading label="טוען את התיק…" />;
  if (error) return <ErrorNote message={error} />;
  if (!c) return <ErrorNote message="התיק לא נמצא." />;

  // Mirrors cases_service.delete_case, which allows both pre-jury phases. The
  // client used to allow only witness_phase, so the two disagreed about a rule
  // that is written down in exactly one place.
  const canWithdraw =
    user?.id === c.author.id && (c.status === "filed" || c.status === "witness_phase");
  const viewer = trial.data?.viewer;

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <PhaseTimeline status={c.status} deadline={c.phase_deadline_at} />

        <Divider sx={{ my: 2 }} />

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <CaseStatusChip status={c.status} deadline={c.phase_deadline_at} />
        </Stack>

        <Typography variant="h4" gutterBottom>
          {c.title}
        </Typography>

        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
          <Avatar
            src={c.author.avatar_url ?? undefined}
            component={RouterLink}
            to={`/users/${c.author.id}`}
          >
            {initials(c.author.name)}
          </Avatar>
          <Box>
            <Typography variant="subtitle2">
              התובע/ת:{" "}
              <Box
                component={RouterLink}
                to={`/users/${c.author.id}`}
                sx={{ color: "primary.main", fontWeight: 700 }}
              >
                {c.author.name}
              </Box>
            </Typography>
            <Typography variant="caption" color="text.secondary">
              הוגשה {relativeTime(c.filed_at)} · {formatDate(c.filed_at)}
            </Typography>
          </Box>
        </Stack>

        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          הנתבע:{" "}
          {c.defendant ? (
            <Box
              component={RouterLink}
              to={`/users/${c.defendant.id}`}
              sx={{ color: "primary.main", fontWeight: 700 }}
            >
              {c.defendant.name}
            </Box>
          ) : (
            <strong>{c.defendant_text}</strong>
          )}
        </Typography>

        {c.charges.length > 0 && (
          <Stack direction="row" spacing={0.75} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
            {c.charges.map((charge) => (
              <Chip key={charge} label={charge} size="small" color="secondary" variant="outlined" />
            ))}
          </Stack>
        )}

        <Divider sx={{ my: 2 }} />

        {c.image_url && (
          <Box
            component="img"
            src={c.image_url}
            alt=""
            // A dead link must not leave a broken-image glyph in the middle of
            // a filing; the case reads fine without it.
            onError={(event) => {
              (event.currentTarget as HTMLImageElement).style.display = "none";
            }}
            sx={{
              display: "block",
              maxWidth: "100%",
              maxHeight: 420,
              borderRadius: 1,
              border: "1px solid",
              borderColor: "divider",
              mb: 2,
            }}
            data-testid="case-image"
          />
        )}

        <Typography sx={{ fontFamily: DOC_FONT, whiteSpace: "pre-wrap", lineHeight: 1.8 }}>
          {c.body}
        </Typography>

        <Divider sx={{ my: 2 }} />

        <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
          <Stack direction="row" spacing={0.5} alignItems="center">
            <LikeButton
              caseId={c.id}
              liked={c.viewer_has_liked}
              count={c.like_count}
              disabled={!user}
            />
            {c.like_count > 0 && (
              <Button size="small" color="inherit" onClick={() => setLikersOpen(true)} data-testid="show-likers">
                מי אהב?
              </Button>
            )}
          </Stack>
          <Stack direction="row" spacing={1}>
            {user && <ReportButton targetType="case" targetId={c.id} />}
            {viewer?.can_summon && (
              <Button
                startIcon={<PersonAddAlt1Icon />}
                onClick={() => setSummonOpen(true)}
                data-testid="summon-button"
              >
                זמן עד ({viewer.summons_remaining})
              </Button>
            )}
            {canWithdraw && (
              <Button color="error" startIcon={<DeleteOutlineIcon />} onClick={withdraw}>
                משוך את התביעה
              </Button>
            )}
          </Stack>
        </Stack>
      </Paper>

      <VerdictBanner
        verdict={c.verdict}
        sentenceText={c.sentence_text}
        judgeName={trial.data?.panel?.judge.name ?? null}
      />

      {viewer?.can_testify && <TestifyForm caseId={c.id} onTestified={reloadAll} />}

      {trial.data && trial.data.summons.length > 0 && (
        <WitnessList summons={trial.data.summons} />
      )}

      {trial.data?.panel && <JuryPanel panel={trial.data.panel} />}

      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="h6" gutterBottom>
          פרוטוקול הדיון
        </Typography>

        {comments.error && <ErrorNote message={comments.error} />}
        {comments.loading && !comments.data && <Loading label="טוען את הפרוטוקול…" />}

        {comments.data && (
          <CommentThread
            comments={comments.data}
            canReply={Boolean(user)}
            onReply={(body, parentId) => addComment(body, parentId)}
          />
        )}

        {/* Likes and comments stay open forever — a verdict ends the trial,
            not the conversation. */}
        {user ? (
          <Box sx={{ mt: 2 }}>
            <CommentComposer
              onSubmit={(body) => addComment(body)}
              assistLoad={() => api.suggestComment(id)}
              assistHint={c.title}
            />
          </Box>
        ) : (
          <Typography color="text.secondary" sx={{ mt: 2 }}>
            יש להתחבר כדי להגיב.
          </Typography>
        )}
      </Paper>

      <LikersDialog open={likersOpen} caseId={c.id} onClose={() => setLikersOpen(false)} />

      <SummonWitnessDialog
        open={summonOpen}
        caseId={c.id}
        remaining={viewer?.summons_remaining ?? 0}
        onClose={() => setSummonOpen(false)}
        onSummoned={reloadAll}
      />
    </Stack>
  );
}; export default CasePage;
