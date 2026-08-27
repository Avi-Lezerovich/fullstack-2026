import { useCallback, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";

import * as api from "../api";
import CaseCard from "../components/feed/CaseCard";
import MySummonsPanel from "../components/trial/MySummonsPanel";
import { EmptyState, ErrorNote, Loading } from "../components/common/StateViews";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../context/AuthContext";
import type { CaseStatus } from "../types";

const PAGE_SIZE = 10;

const FILTERS: { label: string; status?: CaseStatus }[] = [
  { label: "הכול" },
  { label: "איסוף עדויות", status: "witness_phase" },
  { label: "דיוני מושבעים", status: "jury_deliberation" },
  { label: "הוכרעו", status: "verdict_reached" },
];

const Feed = () => {
  const { user } = useAuth();
  const [tab, setTab] = useState(0);
  const [limit, setLimit] = useState(PAGE_SIZE);

  const status = FILTERS[tab].status;
  const load = useCallback(() => api.fetchCases({ limit, status }), [limit, status]);
  const { data, error, loading } = useAsync(load, [limit, status]);

  const cases = data?.cases ?? [];
  const hasMore = data ? cases.length < data.total : false;

  return (
    <Box>
      {/* Above everything: a summons you have not answered is the most
          time-critical thing on this page. */}
      {user && <MySummonsPanel />}

      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "stretch", sm: "center" }}
        spacing={1}
        sx={{ mb: 2 }}
      >
        <Box>
          <Typography variant="h4" gutterBottom>
            אולם בית המשפט
          </Typography>
          <Typography color="text.secondary">
            כל תביעה מקבלת משפט מלא: עדים, חבר מושבעים, ופסק דין.
          </Typography>
        </Box>
        {user && (
          <Button variant="contained" color="secondary" component={RouterLink} to="/cases/new">
            הגש תביעה
          </Button>
        )}
      </Stack>

      <Tabs
        value={tab}
        onChange={(_, next) => {
          setTab(next);
          setLimit(PAGE_SIZE);
        }}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2 }}
      >
        {FILTERS.map((filter) => (
          <Tab key={filter.label} label={filter.label} />
        ))}
      </Tabs>

      {error && <ErrorNote message={error} />}
      {loading && cases.length === 0 && <Loading label="טוען תיקים…" />}

      {!loading && cases.length === 0 && !error && (
        <EmptyState
          title="אין תיקים להצגה"
          description={
            status ? "נסה מסנן אחר." : "היכל המשפט ריק כרגע. אולי כדאי להגיש את התביעה הראשונה?"
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
        <CaseCard key={c.id} case={c} />
      ))}

      {hasMore && (
        <Box sx={{ textAlign: "center", mt: 2 }}>
          <Button onClick={() => setLimit((n) => n + PAGE_SIZE)} disabled={loading}>
            {loading ? "טוען…" : "טען עוד תיקים"}
          </Button>
        </Box>
      )}
    </Box>
  );
}; export default Feed;
