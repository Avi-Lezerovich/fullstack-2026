import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAsync } from "./useAsync";

/**
 * Fetch, spinner, Hebrew error - the three things every page in this app does.
 *
 * The part worth testing is the same stale guard `usePagedList` has, for the
 * same reason and in a different shape: navigating between two cases quickly
 * must not let the first response overwrite the second. It is a `requestId`
 * ref checked at three points - after the await, in the catch, and in the
 * finally - so a late answer can neither set data, nor show its error, nor
 * clear a spinner that belongs to a newer request.
 */

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe("useAsync", () => {
  it("loads on mount and hands back what the loader returned", async () => {
    const loader = vi.fn().mockResolvedValue({ id: 1 });

    const { result } = renderHook(() => useAsync(loader));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ id: 1 });
    expect(result.current.error).toBeNull();
  });

  it("surfaces the server's own Hebrew message", async () => {
    const loader = vi.fn().mockRejectedValue(new Error("התיק המבוקש לא נמצא."));

    const { result } = renderHook(() => useAsync(loader));

    await waitFor(() => expect(result.current.error).toBe("התיק המבוקש לא נמצא."));
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("falls back to a Hebrew message for a failure that is not an Error", async () => {
    const loader = vi.fn().mockRejectedValue("something odd");

    const { result } = renderHook(() => useAsync(loader));

    await waitFor(() => expect(result.current.error).toBe("אירעה שגיאה."));
  });

  it("clears a previous error when it tries again", async () => {
    // Otherwise a successful reload leaves the failure message on screen above
    // the data that has just loaded fine.
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("נכשל"))
      .mockResolvedValueOnce({ id: 2 });

    const { result } = renderHook(() => useAsync(loader));
    await waitFor(() => expect(result.current.error).toBe("נכשל"));

    await act(async () => {
      await result.current.reload();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual({ id: 2 });
  });

  it("reloads when its dependencies change", async () => {
    const loader = vi.fn().mockResolvedValue({ id: 1 });

    const { rerender } = renderHook(({ id }: { id: number }) => useAsync(loader, [id]), {
      initialProps: { id: 1 },
    });
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(1));

    rerender({ id: 2 });

    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
  });

  it("drops a response that belongs to an abandoned request", async () => {
    // Navigating from case 1 to case 2: the first response must not land.
    const slow = deferred<{ id: number }>();
    const fast = deferred<{ id: number }>();
    const loader = vi
      .fn()
      .mockReturnValueOnce(slow.promise)
      .mockReturnValueOnce(fast.promise);

    const { result, rerender } = renderHook(
      ({ id }: { id: number }) => useAsync(loader, [id]),
      { initialProps: { id: 1 } },
    );

    rerender({ id: 2 });

    await act(async () => {
      fast.resolve({ id: 2 });
    });
    await act(async () => {
      slow.resolve({ id: 1 });
    });

    expect(result.current.data).toEqual({ id: 2 });
  });

  it("drops an abandoned request's error too", async () => {
    const slow = deferred<{ id: number }>();
    const fast = deferred<{ id: number }>();
    const loader = vi
      .fn()
      .mockReturnValueOnce(slow.promise)
      .mockReturnValueOnce(fast.promise);

    const { result, rerender } = renderHook(
      ({ id }: { id: number }) => useAsync(loader, [id]),
      { initialProps: { id: 1 } },
    );

    rerender({ id: 2 });

    await act(async () => {
      fast.resolve({ id: 2 });
    });
    await act(async () => {
      slow.reject(new Error("התיק הקודם נכשל"));
    });

    expect(result.current.error).toBeNull();
    expect(result.current.data).toEqual({ id: 2 });
  });
});
