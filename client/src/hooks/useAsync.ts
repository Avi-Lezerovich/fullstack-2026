import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api";

/**
 * Run an async load and expose {data, error, loading, reload}.
 *
 * Every page in this app does the same three things — fetch, show a spinner,
 * show the server's Hebrew error message — and this is that, once. The stale
 * guard matters: navigating between two cases quickly must not let the first
 * response overwrite the second.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
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

  return { data, error, loading, reload: run };
}
