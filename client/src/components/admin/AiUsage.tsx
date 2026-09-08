import { useCallback, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import RefreshIcon from "@mui/icons-material/Refresh";

import * as api from "../../api";
import type {
  BrainFailure,
  CredentialQuota,
  CredentialUsage,
  ProviderUsage,
} from "../../api";
import { EmptyState, ErrorNote, Loading } from "../common/StateViews";
import { useAsync } from "../../hooks/useAsync";
import { quotaSeverity } from "../../utils/adminOps";

const POLL_MS = 30000;

const PROVIDER_LABELS: Record<string, string> = {
  bedrock: "Bedrock",
  anthropic: "Anthropic",
  gemini: "Gemini",
  gateway: "Gateway",
  offline: "מקומי (לא הוגדר)",
};

const RANGES = [
  { label: "היום", key: "today" as const },
  { label: "השבוע האחרון", key: "week" as const },
];

const GROUPINGS = [
  { label: "לפי ספק", key: "provider" as const },
  { label: "לפי מפתח", key: "credential" as const },
];

/**
 * One credential's spend against its allowance.
 *
 * Labelled with the KEY rather than the vendor, because that is the thing that
 * runs out: "Gemini is at 900" says nothing actionable once there are three
 * Gemini keys, and the one that matters is whichever is exhausted. The model
 * is shown too - the free allowance differs by a factor of fifty between two
 * models of the same provider, so a bar without one cannot be checked.
 *
 * `cap: 0` means the allowance is not published (a paid account, or Bedrock).
 * That is stated rather than drawn as a bar, because a progress bar with no
 * denominator is either always empty or always full and means neither.
 */
const CredentialTile = ({ row }: { row: CredentialQuota }) => {
  const severity = quotaSeverity(row.used, row.cap);
  const color = severity === "error" ? "error" : severity === "warning" ? "warning" : "success";

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="credential-quota">
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        {/* Labels and model ids are ASCII inside an RTL page: without an
            explicit direction the browser reorders them. */}
        <Chip size="small" label={row.credential} dir="ltr" />
        <Typography variant="caption" color="text.secondary" dir="ltr" sx={{ fontFamily: "monospace" }}>
          {row.model}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {row.cap > 0 ? (
          <Chip
            size="small"
            color={color}
            label={`${row.used.toLocaleString("he-IL")}/${row.cap.toLocaleString("he-IL")}`}
          />
        ) : (
          <Chip size="small" variant="outlined" label={`${row.used.toLocaleString("he-IL")} קריאות`} />
        )}
      </Stack>
      {row.cap > 0 ? (
        <>
          <LinearProgress
            variant="determinate"
            value={Math.min(100, (row.used / row.cap) * 100)}
            color={color}
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            {row.exhausted
              ? "המכסה נוצלה. הקריאות עוברות למפתח הבא בשרשרת."
              : `נותרו ${row.remaining.toLocaleString("he-IL")} קריאות עד לאיפוס היומי.`}
          </Typography>
        </>
      ) : (
        <Typography variant="caption" color="text.secondary">
          לא הוגדרה מכסה יומית למפתח הזה.
        </Typography>
      )}
    </Paper>
  );
};

const CredentialRow = ({ row }: { row: CredentialUsage }) => (
  <Paper variant="outlined" sx={{ p: 2 }} data-testid="usage-row">
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Chip size="small" label={row.credential} dir="ltr" />
      <Typography variant="caption" color="text.secondary" dir="ltr" sx={{ fontFamily: "monospace" }}>
        {row.model}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {row.calls.toLocaleString("he-IL")} ניסיונות · {row.successes.toLocaleString("he-IL")} הצליחו
        {row.failures > 0 && ` · ${row.failures.toLocaleString("he-IL")} נכשלו`}
        {row.avg_latency_ms > 0 && ` · ${row.avg_latency_ms.toLocaleString("he-IL")} מ״ש בממוצע`}
      </Typography>
    </Stack>
  </Paper>
);

const ProviderRow = ({ row }: { row: ProviderUsage }) => (
  <Paper variant="outlined" sx={{ p: 2 }} data-testid="usage-row">
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Chip size="small" label={PROVIDER_LABELS[row.provider] ?? row.provider} />
      <Typography variant="body2" color="text.secondary">
        {row.calls.toLocaleString("he-IL")} קריאות · {row.successes.toLocaleString("he-IL")} הצליחו
        {row.fallback_to_offline > 0 &&
          ` · ${row.fallback_to_offline.toLocaleString("he-IL")} נפלו למקומי`}
        {row.failures > 0 && ` · ${row.failures.toLocaleString("he-IL")} נכשלו`}
      </Typography>
    </Stack>
    {(row.input_tokens > 0 || row.output_tokens > 0 || row.cache_read > 0) && (
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
        טוקנים: {row.input_tokens.toLocaleString("he-IL")} קלט ·{" "}
        {row.output_tokens.toLocaleString("he-IL")} פלט
        {row.cache_read > 0 && ` · ${row.cache_read.toLocaleString("he-IL")} מהמטמון`}
        {row.cache_write > 0 && ` · ${row.cache_write.toLocaleString("he-IL")} נכתבו למטמון`}
      </Typography>
    )}
  </Paper>
);

/**
 * One failed call's reason, verbatim.
 *
 * `dir="ltr"` and a monospace face are not styling. The page is RTL, and the
 * reason is an English exception string that regularly carries a model id or a
 * URL; rendered in the surrounding direction the browser reorders it and a
 * reader ends up debugging a model name that is not the one that failed.
 */
const FailureRow = ({ row }: { row: BrainFailure }) => (
  <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap" useFlexGap>
    <Chip size="small" color="error" variant="outlined" label={`${row.calls.toLocaleString("he-IL")}×`} />
    <Typography
      variant="caption"
      dir="ltr"
      sx={{ fontFamily: "monospace", wordBreak: "break-word", flex: 1, minWidth: 0 }}
    >
      {row.provider}: {row.reason}
    </Typography>
  </Stack>
);

/**
 * Calls per provider, success vs. fallback, token totals, how close Gemini is
 * to its free tier, and - when calls are failing - why.
 *
 * The quota gauge alone was not enough to run on: a backend where every call
 * errors and a backend that is merely near its cap produce the same climbing
 * number, and the difference between them was sitting unread in
 * `brain_calls.fallback_reason` the whole time.
 */
const AiUsage = () => {
  const load = useCallback(() => api.fetchBrainUsage(), []);
  const { data, error, loading, reload } = useAsync(load, [], POLL_MS);
  const [range, setRange] = useState<"today" | "week">("today");
  const [grouping, setGrouping] = useState<"provider" | "credential">("provider");

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorNote message={error ?? "לא ניתן לטעון את נתוני השימוש."} />;

  const failures = data.failures ?? [];
  const credentials = data.credentials ?? [];
  const rows = data[range];
  const credentialRows = range === "today" ? data.by_credential : data.by_credential_week;

  return (
    <Box data-testid="ai-usage">
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography color="text.secondary">שימוש במנוע הבינה המלאכותית, לפי ספק.</Typography>
        <IconButton size="small" onClick={() => reload()} aria-label="רענן" data-testid="refresh-usage">
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Stack>

      {failures.length > 0 && (
        <Paper
          variant="outlined"
          sx={{ p: 2, mb: 2, borderColor: "error.main" }}
          data-testid="brain-failures"
        >
          <Typography variant="subtitle2" color="error" sx={{ mb: 1 }}>
            כשלים אחרונים (24 שעות)
          </Typography>
          <Stack spacing={0.75}>
            {failures.map((row) => (
              <FailureRow key={`${row.provider}:${row.reason}`} row={row} />
            ))}
          </Stack>
        </Paper>
      )}

      {credentials.length > 0 && (
        <Stack spacing={1.5} sx={{ mb: 2 }}>
          <Typography variant="subtitle2">מכסות יומיות, לפי מפתח</Typography>
          {credentials.map((row) => (
            <CredentialTile key={row.credential} row={row} />
          ))}
        </Stack>
      )}

      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <Tabs
          value={RANGES.findIndex((r) => r.key === range)}
          onChange={(_, next) => setRange(RANGES[next].key)}
        >
          {RANGES.map((r) => (
            <Tab key={r.key} label={r.label} />
          ))}
        </Tabs>
        <Box sx={{ flex: 1 }} />
        <Tabs
          value={GROUPINGS.findIndex((g) => g.key === grouping)}
          onChange={(_, next) => setGrouping(GROUPINGS[next].key)}
          data-testid="usage-grouping"
        >
          {GROUPINGS.map((g) => (
            <Tab key={g.key} label={g.label} />
          ))}
        </Tabs>
      </Stack>

      {grouping === "credential" ? (
        credentialRows.length === 0 ? (
          <EmptyState title="אין נתוני שימוש בטווח הזה" />
        ) : (
          <Stack spacing={1.5}>
            {credentialRows.map((row) => (
              <CredentialRow key={`${row.credential}:${row.model}`} row={row} />
            ))}
          </Stack>
        )
      ) : rows.length === 0 ? (
        <EmptyState title="אין נתוני שימוש בטווח הזה" />
      ) : (
        <Stack spacing={1.5}>
          {rows.map((row) => (
            <ProviderRow key={row.provider} row={row} />
          ))}
        </Stack>
      )}
    </Box>
  );
};

export default AiUsage;
