import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api";

interface Page<T> {
  items: T[];
  total: number;
}

/**
 * An accumulating list: the first page on mount, more pages on request.
 *
 * The point is what it does NOT do. Both lists in this app used to "load more"
 * by asking for a larger `limit` from offset 0 and replacing everything —
 * re-downloading, re-parsing and re-rendering every row already on screen, so
 * the fifth page cost five pages of traffic. Here each page is fetched once,
 * at its own offset, and appended.
 *
 * `deps` identify the query (a search term, a filter tab). Changing them
 * discards what was accumulated and starts again from the top, which is the
 * only correct answer: page three of one query has nothing to do with page
 * three of another.
 */
export function usePagedList<T>(
  fetchPage: (offset: number, limit: number) => Promise<Page<T>>,
  deps: unknown[],
  pageSize: number,
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * Rises on every new query and every reload. A response whose token is no
   * longer current is dropped — without this, typing quickly in a search box
   * lets a slow early response append itself underneath a later one.
   */
  const token = useRef(0);
  const loader = useRef(fetchPage);
  loader.current = fetchPage;

  const load = useCallback(async (offset: number, id: number) => {
    setLoading(true);
    if (offset === 0) setError(null);
    try {
      const page = await loader.current(offset, pageSize);
      if (id !== token.current) return;
      setTotal(page.total);
      setItems((current) => (offset === 0 ? page.items : [...current, ...page.items]));
    } catch (err) {
      if (id !== token.current) return;
      setError(err instanceof ApiError || err instanceof Error ? err.message : "אירעה שגיאה.");
    } finally {
      if (id === token.current) setLoading(false);
    }
  }, [pageSize]);

  const reload = useCallback(() => {
    const id = ++token.current;
    setItems([]);
    setTotal(0);
    void load(0, id);
  }, [load]);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const loadMore = useCallback(() => {
    if (loading) return;
    void load(items.length, token.current);
  }, [load, items.length, loading]);

  return {
    items,
    total,
    error,
    loading,
    hasMore: items.length < total,
    loadMore,
    reload,
  };
}
