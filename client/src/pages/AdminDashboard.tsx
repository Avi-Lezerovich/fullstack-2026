import { useCallback, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import PersonIcon from "@mui/icons-material/Person";
import { Link as RouterLink, Navigate } from "react-router-dom";

import * as api from "../api";
import BannedUsers from "../components/moderation/BannedUsers";
import CourtStatus from "../components/moderation/CourtStatus";
import { EmptyState, ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../context/AuthContext";
import {
  MODERATION_STATUS_LABELS,
  REPORT_STATUS_LABELS,
  type FlaggedItem,
  type ModerationAction,
  type ModerationStatus,
  type Report,
} from "../types";
import { relativeTime } from "../utils/format";

const QUEUE_TABS = [
  { label: "ממתינים", status: "open" },
  { label: "בבדיקה", status: "claimed" },
  { label: "טופלו", status: "resolved" },
] as const;

const AuditTrail = ({ targetType, targetId }: { targetType: string; targetId: number }) => {
  const [history, setHistory] = useState<ModerationAction[] | null>(null);
  const [open, setOpen] = useState(false);

  const toggle = async () => {
    if (!open && history === null) {
      setHistory(await api.fetchModerationHistory(targetType, targetId));
    }
    setOpen((value) => !value);
  };

  return (
    <Box sx={{ mt: 1 }}>
      <Button size="small" onClick={toggle}>
        {open ? "הסתר היסטוריה" : "היסטוריית פיקוח"}
      </Button>
      {open && (
        <Stack spacing={0.5} sx={{ mt: 1 }} data-testid="audit-trail">
          {(history ?? []).length === 0 && (
            <Typography variant="caption" color="text.secondary">
              לא בוצעו פעולות פיקוח.
            </Typography>
          )}
          {(history ?? []).map((entry) => (
            <Stack key={entry.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              {entry.actor_is_bot ? (
                <SmartToyIcon fontSize="inherit" color="disabled" />
              ) : (
                <PersonIcon fontSize="inherit" color="primary" />
              )}
              <Typography variant="caption">
                <strong>{entry.actor.name}</strong> · {entry.action}
                {entry.previous_status && ` · ${entry.previous_status} ← ${entry.new_status}`}
                {entry.reason && ` · ${entry.reason}`} · {relativeTime(entry.created_at)}
              </Typography>
            </Stack>
          ))}
        </Stack>
      )}
    </Box>
  );
};

const ReportRow = ({ report, onChanged }: { report: Report; onChanged: () => void }) => {
  const [failure, setFailure] = useState<string | null>(null);

  const resolve = async (decision: string) => {
    setFailure(null);
    try {
      await api.resolveReport(report.id, decision, "הוכרע על ידי מנהל.");
      onChanged();
    } catch (err) {
      // A refusal is meaningful here — "you cannot ban yourself" is a real
      // answer, and swallowing it would look like the button did nothing.
      setFailure(err instanceof Error ? err.message : "הפעולה נכשלה.");
    }
  };

  const resolved = report.status.startsWith("resolved");

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="report-row">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip size="small" label={REPORT_STATUS_LABELS[report.status]} />
        <Typography variant="caption" color="text.secondary">
          {report.target_type === "case" ? "תיק" : "תגובה"} #{report.target_id} · דווח על ידי{" "}
          {report.reporter.name} · {relativeTime(report.created_at)} · סיבה: {report.reason}
        </Typography>
      </Stack>

      <Typography variant="body2" sx={{ mt: 1, fontStyle: "italic" }}>
        “{report.excerpt}”
      </Typography>

      {failure && <ErrorNote message={failure} />}

      {report.resolution_note && (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
          {report.resolver?.name}: {report.resolution_note}
        </Typography>
      )}

      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        {/* A comment is only judgeable in context, and its case is now on the
            report payload — before this the row was a 200-character excerpt
            with nowhere to go. */}
        {report.case_id !== null && (
          <Button size="small" component={RouterLink} to={`/cases/${report.case_id}`}>
            {report.target_type === "case" ? "הצג תיק" : "הצג בהקשר"}
          </Button>
        )}
        {!resolved && (
          <>
            <Button size="small" onClick={() => resolve("resolved_dismissed")}>
              דחה דיווח
            </Button>
            {/* This really does hide the content now, so it says so. It used
                to be labelled "mark handled" while changing nothing but the
                report's own status. */}
            <Button size="small" color="error" onClick={() => resolve("resolved_hidden")}>
              הסתר את התוכן
            </Button>
            {/* Hides the content AND suspends its author, revoking every
                session. Confirmed first, because it is the heaviest thing an
                admin can do from this screen. */}
            <Button
              size="small"
              color="error"
              variant="outlined"
              onClick={() => {
                if (window.confirm("להסתיר את התוכן ולהשעות את המשתמש? אפשר לבטל בלשונית המושעים.")) {
                  void resolve("resolved_banned");
                }
              }}
              data-testid="ban-from-report"
            >
              הסתר והשעה את המשתמש
            </Button>
          </>
        )}
      </Stack>

      <AuditTrail targetType={report.target_type} targetId={report.target_id} />
    </Paper>
  );
};

const FlaggedRow = ({ item, onChanged }: { item: FlaggedItem; onChanged: () => void }) => {
  const change = async (status: ModerationStatus) => {
    await api.setContentStatus(item.target_type, item.target_id, status, "החלטת מנהל.");
    onChanged();
  };

  const hidden = item.moderation_status === "hidden" || item.moderation_status === "rejected";

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="flagged-row">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip
          size="small"
          color={hidden ? "error" : "warning"}
          label={MODERATION_STATUS_LABELS[item.moderation_status]}
        />
        <Typography variant="caption" color="text.secondary">
          {item.target_type === "case" ? "תיק" : "תגובה"} #{item.target_id} · מאת{" "}
          {item.author.name} · {relativeTime(item.created_at)}
        </Typography>
      </Stack>

      {item.heading && (
        <Typography variant="subtitle2" sx={{ mt: 1 }}>
          {item.heading}
        </Typography>
      )}
      <Typography variant="body2" sx={{ mt: 0.5, fontStyle: "italic" }}>
        “{item.excerpt}”
      </Typography>

      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        {/* The override the course requires: any bot decision can be reversed,
            and the reversal is recorded in the audit trail below. */}
        {hidden ? (
          <Button size="small" variant="contained" onClick={() => change("published")}>
            החזר לפרסום
          </Button>
        ) : (
          <Button size="small" color="error" onClick={() => change("hidden")}>
            הסתר
          </Button>
        )}
        <Button size="small" onClick={() => change("flagged")}>
          סמן לבדיקה
        </Button>
      </Stack>

      <AuditTrail targetType={item.target_type} targetId={item.target_id} />
    </Paper>
  );
};

type View = "reports" | "flagged" | "banned";

const VIEWS: { id: View; label: string }[] = [
  { id: "reports", label: "תור הדיווחים" },
  { id: "flagged", label: "תוכן מסומן" },
  { id: "banned", label: "משתמשים מושעים" },
];

const AdminDashboard = () => {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState(0);
  const [view, setView] = useState<View>("reports");

  const status = QUEUE_TABS[tab].status;
  const reports = useAsync(useCallback(() => api.fetchReportQueue(status), [status]), [status]);
  const flagged = useAsync(useCallback(() => api.fetchFlagged(), []), []);

  if (loading) return <Loading />;
  if (!user?.is_admin) return <Navigate to="/" replace />;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        לשכת הפיקוח
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        בוטי הפיקוח מטפלים בתור באופן שוטף. כל החלטה שלהם ניתנת לביטול כאן, וכל שינוי נרשם ביומן.
      </Typography>

      <CourtStatus />

      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        {VIEWS.map((option) => (
          <Button
            key={option.id}
            variant={view === option.id ? "contained" : "outlined"}
            onClick={() => setView(option.id)}
            data-testid={`admin-view-${option.id}`}
          >
            {option.label}
          </Button>
        ))}
      </Stack>

      {view === "banned" ? (
        <BannedUsers />
      ) : view === "flagged" ? (
        <>
          {flagged.error && <ErrorNote message={flagged.error} />}
          {flagged.loading && !flagged.data && <Loading />}
          {flagged.data?.length === 0 && <EmptyState title="אין תוכן מסומן" />}
          <Stack spacing={1.5}>
            {flagged.data?.map((item) => (
              <FlaggedRow
                key={`${item.target_type}-${item.target_id}`}
                item={item}
                onChanged={flagged.reload}
              />
            ))}
          </Stack>
        </>
      ) : (
        <>
          <Tabs value={tab} onChange={(_, next) => setTab(next)} sx={{ mb: 2 }}>
            {QUEUE_TABS.map((t) => (
              <Tab key={t.status} label={t.label} />
            ))}
          </Tabs>

          {reports.error && <ErrorNote message={reports.error} />}
          {reports.loading && !reports.data && <Loading />}
          {reports.data?.length === 0 && <EmptyState title="אין דיווחים בקטגוריה הזו" />}
          <Stack spacing={1.5}>
            {reports.data?.map((report) => (
              <ReportRow key={report.id} report={report} onChanged={reports.reload} />
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}; export default AdminDashboard;
