import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api";

/**
 * Run an async load and expose {data, error, loading, reload}.
 *
 * Every page in this app does the same three things — fetch, show a spinner,
 * show the server's Hebrew error message — and this is that, once. The stale
 * guard matters: navigating between two cases quickly must not let the first
 * response overwrite the second.
 *
 * `intervalMs`, when given, re-runs `run` on that cadence in the background —
 * for a live status view where reloading the whole page just to see a fresh
 * number would be worse than the number being briefly stale. It reuses `run`
 * rather than `reload`, so a background tick still respects the same stale
 * guard as a manual one.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = [], intervalMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const requestId = useRef(0);

  const run = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await loader();
      if (id === requestId.current) setData(result);
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof ApiError || err instanceof Error ? err.message : "אירעה שגיאה.");
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void run();
  }, [run]);

  useEffect(() => {
    if (!intervalMs) return undefined;
    const id = setInterval(() => void run(), intervalMs);
    return () => clearInterval(id);
  }, [run, intervalMs]);

  return { data, error, loading, reload: run };
}
