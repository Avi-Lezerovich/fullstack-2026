import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePagedList } from "./usePagedList";

/**
 * The accumulating list.
 *
 * Every test here drives a `fetchPage` the test itself controls, because the
 * three things worth pinning are all about WHEN the hook calls it and what it
 * does with an answer that arrives late:
 *
 *   - the offset comes from what has accumulated, not from a page counter;
 *   - a response whose token is stale is dropped rather than appended;
 *   - an empty later page ends the list whatever `total` claims.
 *
 * `deferred()` hands back a promise plus its resolver, which is what lets a
 * test resolve page one AFTER a dependency change - the ordering the token
 * exists for and the only way to reproduce it deterministically.
 */

interface Row {
  id: number;
}

const page = (ids: number[], total: number) => ({
  items: ids.map((id) => ({ id })),
  total,
});

/** A promise the test resolves by hand, so response order is a choice. */
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe("usePagedList", () => {
  it("loads the first page on mount", async () => {
    const fetchPage = vi.fn().mockResolvedValue(page([1, 2], 5));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchPage).toHaveBeenCalledWith(0, 2);
    expect(result.current.items).toHaveLength(2);
    expect(result.current.total).toBe(5);
    expect(result.current.hasMore).toBe(true);
  });

  it("asks for the next page at the offset it has already accumulated", async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([1, 2], 5))
      .mockResolvedValueOnce(page([3, 4], 5));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Not "page 2" — the offset is items.length, so it stays correct even if
    // a page came back short.
    expect(fetchPage).toHaveBeenLastCalledWith(2, 2);
  });

  it("appends the next page instead of replacing what is on screen", async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([1, 2], 4))
      .mockResolvedValueOnce(page([3, 4], 4));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(4));

    expect(result.current.items.map((row) => row.id)).toEqual([1, 2, 3, 4]);
    expect(result.current.hasMore).toBe(false);
  });

  it("does not stack a second page request on top of one already in flight", async () => {
    const first = deferred<{ items: Row[]; total: number }>();
    const fetchPage = vi.fn().mockReturnValue(first.promise);

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));

    act(() => result.current.loadMore());

    expect(fetchPage).toHaveBeenCalledTimes(1);

    await act(async () => {
      first.resolve(page([1, 2], 4));
    });
  });

  it("drops a response whose query is no longer the current one", async () => {
    // The regression the token exists for: type quickly in a search box and a
    // slow early response appends itself underneath a later one.
    const slow = deferred<{ items: Row[]; total: number }>();
    const fast = deferred<{ items: Row[]; total: number }>();
    const fetchPage = vi
      .fn()
      .mockReturnValueOnce(slow.promise)
      .mockReturnValueOnce(fast.promise);

    const { result, rerender } = renderHook(
      ({ term }: { term: string }) => usePagedList<Row>(fetchPage, [term], 2),
      { initialProps: { term: "a" } },
    );

    rerender({ term: "ab" });

    await act(async () => {
      fast.resolve(page([9], 1));
    });
    // Page one of the ABANDONED query, arriving last.
    await act(async () => {
      slow.resolve(page([1, 2], 2));
    });

    expect(result.current.items.map((row) => row.id)).toEqual([9]);
    expect(result.current.total).toBe(1);
  });

  it("drops a stale failure too, so an abandoned query cannot show its error", async () => {
    const slow = deferred<{ items: Row[]; total: number }>();
    const fast = deferred<{ items: Row[]; total: number }>();
    const fetchPage = vi
      .fn()
      .mockReturnValueOnce(slow.promise)
      .mockReturnValueOnce(fast.promise);

    const { result, rerender } = renderHook(
      ({ term }: { term: string }) => usePagedList<Row>(fetchPage, [term], 2),
      { initialProps: { term: "a" } },
    );

    rerender({ term: "ab" });

    await act(async () => {
      fast.resolve(page([9], 1));
    });
    await act(async () => {
      slow.reject(new Error("הבקשה הקודמת נכשלה"));
    });

    expect(result.current.error).toBeNull();
    expect(result.current.items).toHaveLength(1);
  });

  it("starts again from the top when the query changes", async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([1, 2], 4))
      .mockResolvedValueOnce(page([7], 1));

    const { result, rerender } = renderHook(
      ({ term }: { term: string }) => usePagedList<Row>(fetchPage, [term], 2),
      { initialProps: { term: "a" } },
    );
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    rerender({ term: "b" });
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    // Page three of one query has nothing to do with page three of another.
    expect(fetchPage).toHaveBeenLastCalledWith(0, 2);
    expect(result.current.items.map((row) => row.id)).toEqual([7]);
  });

  it("ends the list on an empty later page whatever the total claims", async () => {
    // `total` and the rows can disagree honestly — something was withdrawn or
    // hidden between the two requests. Believing `total` leaves hasMore true
    // forever, which with the scroll sentinel is a request loop.
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([1, 2], 10))
      .mockResolvedValueOnce(page([], 10));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.hasMore).toBe(false));

    expect(result.current.total).toBe(2);
    expect(result.current.items).toHaveLength(2);
  });

  it("still believes a total larger than the first page", async () => {
    // The correction above must not fire on page one, or a list longer than
    // one page could never be paged at all.
    const fetchPage = vi.fn().mockResolvedValue(page([], 10));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.total).toBe(10);
  });

  it("surfaces the server's own message when a page fails", async () => {
    const fetchPage = vi.fn().mockRejectedValue(new Error("התיק המבוקש לא נמצא."));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));

    await waitFor(() => expect(result.current.error).toBe("התיק המבוקש לא נמצא."));
    expect(result.current.loading).toBe(false);
  });

  it("falls back to a Hebrew message when the failure is not an Error", async () => {
    const fetchPage = vi.fn().mockRejectedValue("something odd");

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));

    await waitFor(() => expect(result.current.error).toBe("אירעה שגיאה."));
  });

  it("reload discards what was accumulated and fetches from zero", async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([1, 2], 4))
      .mockResolvedValueOnce(page([3, 4], 4))
      .mockResolvedValueOnce(page([5, 6], 4));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(4));

    act(() => result.current.reload());
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    expect(fetchPage).toHaveBeenLastCalledWith(0, 2);
    expect(result.current.items.map((row) => row.id)).toEqual([5, 6]);
  });

  it("rewrites a row in place without disturbing the pages around it", async () => {
    // patchItems exists so liking from the feed redraws one number. reload()
    // would also be truthful and would throw away every page loaded so far,
    // scrolling the reader back to the top to change a single digit.
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([1, 2], 4))
      .mockResolvedValueOnce(page([3, 4], 4));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.items).toHaveLength(4));

    act(() => result.current.patchItems((row) => (row.id === 3 ? { id: 30 } : row)));

    expect(result.current.items.map((row) => row.id)).toEqual([1, 2, 30, 4]);
    expect(result.current.total).toBe(4);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it("patching leaves an unrelated row untouched by identity", async () => {
    const fetchPage = vi.fn().mockResolvedValue(page([1, 2], 2));

    const { result } = renderHook(() => usePagedList<Row>(fetchPage, [], 2));
    await waitFor(() => expect(result.current.items).toHaveLength(2));
    const before = result.current.items[1];

    act(() => result.current.patchItems((row) => (row.id === 1 ? { id: 11 } : row)));

    expect(result.current.items[1]).toBe(before);
  });
});
