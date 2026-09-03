import { useCallback, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
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
  id: string;
  label: string;
  status?: CaseStatus;
  /** The personal feed reads a different endpoint and sorts by activity. */
  mine?: boolean;
}

const FILTERS: FeedTab[] = [
  { id: "all", label: "הכול" },
  { id: "witness_phase", label: "איסוף עדויות", status: "witness_phase" },
  { id: "jury_deliberation", label: "דיוני מושבעים", status: "jury_deliberation" },
  { id: "verdict_reached", label: "הוכרעו", status: "verdict_reached" },
];

const MY_FEED: FeedTab = { id: "mine", label: "הפיד שלי", mine: true };

const Feed = () => {
  const { user } = useAuth();

  /**
   * The open tab is tracked by id rather than by index, and starts on the
   * courtroom rather than on the personal feed.
   *
   * By id, because `user` resolves a moment after mount: the personal feed
   * appears in FRONT of the list when it does, and an index would quietly come
   * to mean the tab next door. By id it means the same tab throughout, and
   * signing out - which takes the personal feed away entirely - falls back to
   * the courtroom instead of pointing at nothing.
   *
   * On the courtroom, because a new account follows nothing yet, and landing
   * every signed-in visitor on an empty state to reach a feature they have not
   * used is a poor trade for one tap.
   */
  const [activeId, setActiveId] = useState(FILTERS[0].id);

  const tabs = useMemo(() => (user ? [MY_FEED, ...FILTERS] : FILTERS), [user]);
  const index = Math.max(
    tabs.findIndex((candidate) => candidate.id === activeId),
    0,
  );
  const active = tabs[index];

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
    // Pulled up against the top bar. The shared Container's `py: 3` is right
    // for a page that opens with a heading; this one opens with a control
    // strip, and the full gap left it floating.
    <Box sx={{ mt: -2 }}>
      {/* Above everything: a summons you have not answered is the most
          time-critical thing on this page. */}
      {user && <MySummonsPanel />}

      {/* Tabs and the file-a-lawsuit button share one line: they are the only
          two controls on the page, and stacking them cost a whole row of empty
          space between the top bar and the first case. */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
        sx={{ mb: 2 }}
      >
        <Tabs
          value={index}
          onChange={(_, next) => setActiveId(tabs[next].id)}
          variant="scrollable"
          scrollButtons="auto"
          // minWidth lets the scroller shrink instead of shoving the button
          // off the row on a narrow screen.
          sx={{ flex: 1, minWidth: 0 }}
        >
          {tabs.map((filter) => (
            <Tab key={filter.id} label={filter.label} />
          ))}
        </Tabs>
        {user && (
          <Button
            variant="contained"
            color="secondary"
            component={RouterLink}
            to="/cases/new"
            sx={{ flexShrink: 0 }}
          >
            הגש תביעה
          </Button>
        )}
      </Stack>

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
