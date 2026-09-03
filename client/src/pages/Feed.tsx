import { useCallback, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../api";
import CaseCard from "../components/feed/CaseCard";
import MySummonsPanel from "../components/trial/MySummonsPanel";
import { EmptyState, ErrorNote, Loading } from "../components/common/StateViews";
import { usePagedList } from "../hooks/usePagedList";
import { useAuth } from "../context/AuthContext";
import type { CaseStatus } from "../types";

const PAGE_SIZE = 10;

interface FeedTab {
  label: string;
  status?: CaseStatus;
  /** The personal feed reads a different endpoint and sorts by activity. */
  mine?: boolean;
}

const FILTERS: FeedTab[] = [
  { label: "הכול" },
  { label: "איסוף עדויות", status: "witness_phase" },
  { label: "דיוני מושבעים", status: "jury_deliberation" },
  { label: "הוכרעו", status: "verdict_reached" },
];

const MY_FEED: FeedTab = { label: "הפיד שלי", mine: true };

const Feed = () => {
  const { user } = useAuth();
  const [tab, setTab] = useState(0);

  // Signed out there is no personal feed, so the tabs are exactly what they
  // always were and no index shifts underneath anybody.
  const tabs = useMemo(() => (user ? [MY_FEED, ...FILTERS] : FILTERS), [user]);
  const active = tabs[tab] ?? tabs[0];

  const loadPage = useCallback(
    async (offset: number, limit: number) => {
      const page = active.mine
        ? await api.fetchMyFeed({ limit, offset })
        : await api.fetchCases({ limit, offset, status: active.status });
      return { items: page.cases, total: page.total };
    },
    [active],
  );
  const {
    items: cases,
    error,
    loading,
    hasMore,
    loadMore,
  } = usePagedList(loadPage, [active], PAGE_SIZE);

  return (
    <Box>
      {/* Above everything: a summons you have not answered is the most
          time-critical thing on this page. */}
      {user && <MySummonsPanel />}

      {user && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
          <Button variant="contained" color="secondary" component={RouterLink} to="/cases/new">
            הגש תביעה
          </Button>
        </Box>
      )}

      <Tabs
        value={tab}
        onChange={(_, next) => setTab(next)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2 }}
      >
        {tabs.map((filter) => (
          <Tab key={filter.label} label={filter.label} />
        ))}
      </Tabs>

      {error && <ErrorNote message={error} />}
      {loading && cases.length === 0 && <Loading label="טוען תיקים…" />}

      {!loading && cases.length === 0 && !error && active.mine && (
        <EmptyState
          title="אינך עוקב עדיין אחרי אף תביעה"
          description="עקוב אחרי תיק כדי לראות כאן כל תגובה, עדות והכרעה לפי סדר הזמן."
        />
      )}

      {!loading && cases.length === 0 && !error && !active.mine && (
        <EmptyState
          title="אין תיקים להצגה"
          description={
            active.status
              ? "נסה מסנן אחר."
              : "היכל המשפט ריק כרגע. אולי כדאי להגיש את התביעה הראשונה?"
          }
          action={
            user ? (
              <Button variant="contained" component={RouterLink} to="/cases/new">
                הגש תביעה
              </Button>
            ) : undefined
          }
        />
      )}

      {cases.map((c) => (
        <CaseCard key={c.id} case={c} showActivity={active.mine} canFollow={Boolean(user)} />
      ))}

      {hasMore && (
        <Box sx={{ textAlign: "center", mt: 2 }}>
          <Button onClick={loadMore} disabled={loading}>
            {loading ? "טוען…" : "טען עוד תיקים"}
          </Button>
        </Box>
      )}
    </Box>
  );
}; export default Feed;
