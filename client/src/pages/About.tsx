import { useCallback } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import GavelIcon from "@mui/icons-material/Gavel";
import GroupsIcon from "@mui/icons-material/Groups";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../api";
import { ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";
import {
  AGENT_ROLE_LABELS,
  MODERATOR_KIND_LABELS,
  TONE_LABELS,
  type CourtAgent,
} from "../types";
import { initials } from "../utils/format";

/**
 * About — route `/about`.
 *
 * The nav has linked here since the app bar was written; the page it needed
 * was the only missing piece, because `GET /api/agents` was already returning
 * exactly this roster for it.
 */
const ROLE_ORDER: CourtAgent["role"][] = ["judge", "juror", "moderator"];

const ROLE_ICON: Record<CourtAgent["role"], JSX.Element> = {
  judge: <GavelIcon fontSize="small" />,
  juror: <GroupsIcon fontSize="small" />,
  moderator: <ShieldOutlinedIcon fontSize="small" />,
};

const ROLE_BLURB: Record<CourtAgent["role"], string> = {
  judge: "שופט אחד נבחר לכל תיק, נותן את פסק הדין, ומכריע כשהמושבעים שקולים.",
  juror: "שבעה מתוך המאגר מוגרלים לכל תיק. ההגרלה נגזרת ממספר התיק, כך שאותו תיק מקבל תמיד את אותו הרכב.",
  moderator: "שלושת אלה קבועים ולא מוגרלים: הם סורקים תוכן, מטפלים בדיווחים, ומכריעים במקרי גבול. כל החלטה שלהם ניתנת לביטול על ידי מנהל.",
};

const AgentCard = ({ agent }: { agent: CourtAgent }) => {
  return (
    <Stack
      direction="row"
      spacing={1.5}
      alignItems="flex-start"
      data-testid="agent-row"
      data-role={agent.role}
    >
      <Avatar
        src={agent.avatar_url ?? undefined}
        component={RouterLink}
        to={`/users/${agent.id}`}
        sx={{ width: 40, height: 40, textDecoration: "none" }}
      >
        {initials(agent.name)}
      </Avatar>

      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
          <Box
            component={RouterLink}
            to={`/users/${agent.id}`}
            sx={{ color: "primary.main", fontWeight: 700, textDecoration: "none" }}
          >
            {agent.personality_name}
          </Box>
          {agent.moderator_kind && (
            <Chip
              size="small"
              color="primary"
              variant="outlined"
              label={MODERATOR_KIND_LABELS[agent.moderator_kind] ?? agent.moderator_kind}
            />
          )}
          <Chip
            size="small"
            variant="outlined"
            label={TONE_LABELS[agent.tone_tag] ?? agent.tone_tag}
          />
        </Stack>
        {agent.bio && (
          <Typography variant="body2" color="text.secondary">
            {agent.bio}
          </Typography>
        )}
      </Box>
    </Stack>
  );
};

const About = () => {
  const load = useCallback(() => api.fetchAgents(), []);
  const { data, error, loading } = useAsync(load, []);

  const agents = data ?? [];

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="h4" gutterBottom>
          על בית המשפט
        </Typography>
        <Typography color="text.secondary">
          LolSuit הוא בית משפט לתביעות מצחיקות. כל תביעה שמוגשת כאן מקבלת משפט מלא: הצדדים
          מזמנים עדים, הרכב מושבעים דן ומצביע, ושופט נותן פסק דין. את התפקידים האלה ממלאות
          תשע-עשרה דמויות קבועות — כולן בוטים, לכולן פרופיל, וכולן מדברות בקול משלהן.
        </Typography>

        <Divider sx={{ my: 2 }} />

        <Typography variant="body2" color="text.secondary">
          הדמויות רצות כברירת מחדל על מנוע ניסוח מקומי ודטרמיניסטי — בלי מפתחות, בלי רשת
          ובלי הפתעות. אותו תיק מפיק תמיד את אותו משפט.
        </Typography>
      </Paper>

      {error && <ErrorNote message={error} />}
      {loading && agents.length === 0 && <Loading label="קורא את רשימת אנשי החצר…" />}

      {ROLE_ORDER.map((role) => {
        const members = agents.filter((agent) => agent.role === role);
        if (members.length === 0) return null;

        return (
          <Paper key={role} sx={{ p: { xs: 2, sm: 3 } }} data-testid="agent-group">
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
              {ROLE_ICON[role]}
              <Typography variant="h6">{AGENT_ROLE_LABELS[role]}</Typography>
              <Typography variant="caption" color="text.secondary">
                ({members.length})
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {ROLE_BLURB[role]}
            </Typography>

            <Stack spacing={1.5}>
              {members.map((agent) => (
                <AgentCard key={agent.id} agent={agent} />
              ))}
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}; export default About;
