import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useNotificationStream } from "./useNotificationStream";
import type { Notification } from "../types";

/**
 * SSE where it works, polling where it does not.
 *
 * jsdom has no EventSource, so the stub below is both the fake and the
 * mechanism: it records every stream that was opened and hands the test the
 * two triggers that matter — deliver a frame, and fail.
 *
 * The behaviour worth pinning is the fallback, and specifically that it is
 * ONE-WAY. Falling back is permanent for the session rather than retried
 * forever: if a proxy is buffering event streams, reconnecting will not fix
 * it, and a reconnect loop is worse than polling. So the tests below check
 * both halves — that a single failure reconnects, and that two inside the
 * window stop trying for good.
 */

interface Stream {
  url: string;
  listeners: Record<string, (event: MessageEvent) => void>;
  onerror: (() => void) | null;
  closed: boolean;
}

let streams: Stream[] = [];

/**
 * The fetch stub, kept as a handle rather than read back off the global.
 *
 * `globalThis.fetch` is typed as the real thing, so asserting on it would need
 * a cast at every call site - and `global` is not in tsconfig's `types` list
 * at all, so `npm run lint` rejects it outright.
 */
let polls: ReturnType<typeof vi.fn>;

const stubFetch = (
  impl: () => Promise<unknown> = async () => ({ ok: true, json: async () => ({ notifications: [] }) }),
) => {
  polls = vi.fn(impl);
  vi.stubGlobal("fetch", polls);
};

class FakeEventSource {
  private stream: Stream;

  constructor(url: string) {
    this.stream = { url, listeners: {}, onerror: null, closed: false };
    streams.push(this.stream);
  }

  addEventListener(name: string, handler: (event: MessageEvent) => void) {
    this.stream.listeners[name] = handler;
  }

  set onerror(handler: () => void) {
    this.stream.onerror = handler;
  }

  close() {
    this.stream.closed = true;
  }
}

/** Push one notification down the newest open stream. */
const deliver = (notification: Partial<Notification> & { id: number }) => {
  const stream = streams[streams.length - 1];
  stream.listeners.notification?.({
    data: JSON.stringify(notification),
  } as MessageEvent);
};

/** Break the newest stream, the way a proxy closing the connection would. */
const breakStream = () => streams[streams.length - 1].onerror?.();

const notification = (id: number): Notification =>
  ({ id, type: "like", payload: {}, is_read: false }) as unknown as Notification;

beforeEach(() => {
  streams = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  stubFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useNotificationStream", () => {
  it("opens nothing at all while it is disabled", () => {
    // NotificationContext gates on a `loaded` flag, because at since=0 the
    // server replays the user's entire history and every row arrives new.
    renderHook(() =>
      useNotificationStream({ enabled: false, since: 0, onNotification: vi.fn() }),
    );

    expect(streams).toHaveLength(0);
  });

  it("opens a stream from the cursor it was given", () => {
    renderHook(() =>
      useNotificationStream({ enabled: true, since: 42, onNotification: vi.fn() }),
    );

    expect(streams).toHaveLength(1);
    expect(streams[0].url).toContain("since=42");
  });

  it("hands every frame to the callback", () => {
    const onNotification = vi.fn();
    renderHook(() => useNotificationStream({ enabled: true, since: 0, onNotification }));

    act(() => deliver(notification(1)));
    act(() => deliver(notification(2)));

    expect(onNotification).toHaveBeenCalledTimes(2);
    expect(onNotification.mock.calls[1][0].id).toBe(2);
  });

  it("ignores a frame it cannot parse rather than tearing down the stream", () => {
    const onNotification = vi.fn();
    renderHook(() => useNotificationStream({ enabled: true, since: 0, onNotification }));

    act(() => {
      streams[0].listeners.notification?.({ data: "not json" } as MessageEvent);
    });

    expect(onNotification).not.toHaveBeenCalled();
    expect(streams[0].closed).toBe(false);

    act(() => deliver(notification(1)));
    expect(onNotification).toHaveBeenCalledTimes(1);
  });

  it("reconnects once, because the server caps every stream's lifetime", () => {
    // A clean close is the NORMAL case here, not an error — so one failure
    // must not be enough to conclude that SSE is broken.
    vi.useFakeTimers();
    renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );

    act(() => breakStream());
    act(() => void vi.advanceTimersByTime(1000));

    expect(streams).toHaveLength(2);
    expect(polls).not.toHaveBeenCalled();
  });

  it("resumes a reconnect from the last id it actually saw", () => {
    vi.useFakeTimers();
    renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );

    act(() => deliver(notification(7)));
    act(() => breakStream());
    act(() => void vi.advanceTimersByTime(1000));

    expect(streams[1].url).toContain("since=7");
  });

  it("gives up on SSE for good after two failures inside the window", async () => {
    vi.useFakeTimers();
    renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );

    act(() => breakStream());
    act(() => void vi.advanceTimersByTime(1000));
    act(() => breakStream());

    // Polling started, and no third stream was opened.
    expect(polls).toHaveBeenCalledTimes(1);
    expect(streams).toHaveLength(2);

    act(() => void vi.advanceTimersByTime(5000));
    expect(streams).toHaveLength(2);
  });

  it("keeps polling on its own interval once it has fallen back", () => {
    vi.useFakeTimers();
    renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );

    act(() => breakStream());
    act(() => void vi.advanceTimersByTime(1000));
    act(() => breakStream());

    act(() => void vi.advanceTimersByTime(10_000));
    act(() => void vi.advanceTimersByTime(10_000));

    expect(polls).toHaveBeenCalledTimes(3);
  });

  it("polls straight away where the browser has no EventSource at all", () => {
    vi.stubGlobal("EventSource", undefined);

    renderHook(() =>
      useNotificationStream({ enabled: true, since: 5, onNotification: vi.fn() }),
    );

    expect(polls).toHaveBeenCalledTimes(1);
    expect(polls.mock.calls[0][0]).toContain("since=5");
  });

  it("polling advances the same cursor and calls the same callback", async () => {
    vi.stubGlobal("EventSource", undefined);
    stubFetch(async () => ({
      ok: true,
      json: async () => ({ notifications: [notification(11), notification(12)] }),
    }));
    const onNotification = vi.fn();

    renderHook(() => useNotificationStream({ enabled: true, since: 0, onNotification }));

    // Both transports are interchangeable to every consumer, which is exactly
    // why the polling path could ship first and SSE be layered on after.
    await waitFor(() => expect(onNotification).toHaveBeenCalledTimes(2));
    expect(onNotification.mock.calls[1][0].id).toBe(12);
  });

  it("sends the session cookie when it polls", async () => {
    vi.stubGlobal("EventSource", undefined);

    renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );

    await waitFor(() => expect(polls).toHaveBeenCalled());
    const [, options] = polls.mock.calls[0];
    expect(options.credentials).toBe("include");
  });

  it("a failed poll is swallowed rather than surfaced", async () => {
    vi.stubGlobal("EventSource", undefined);
    stubFetch(async () => {
      throw new Error("offline");
    });
    const onNotification = vi.fn();

    renderHook(() => useNotificationStream({ enabled: true, since: 0, onNotification }));

    await waitFor(() => expect(polls).toHaveBeenCalled());
    expect(onNotification).not.toHaveBeenCalled();
  });

  it("a non-ok poll delivers nothing", async () => {
    vi.stubGlobal("EventSource", undefined);
    stubFetch(async () => ({ ok: false, json: async () => ({}) }));
    const onNotification = vi.fn();

    renderHook(() => useNotificationStream({ enabled: true, since: 0, onNotification }));

    await waitFor(() => expect(polls).toHaveBeenCalled());
    expect(onNotification).not.toHaveBeenCalled();
  });

  it("the cursor only ever moves forwards", () => {
    const onNotification = vi.fn();
    const { rerender } = renderHook(
      ({ since }: { since: number }) =>
        useNotificationStream({ enabled: true, since, onNotification }),
      { initialProps: { since: 10 } },
    );

    // A parent recomputing a lower `since` must not rewind the stream and
    // replay what the user has already been shown.
    rerender({ since: 3 });
    vi.useFakeTimers();
    act(() => breakStream());
    act(() => void vi.advanceTimersByTime(1000));

    expect(streams[1].url).toContain("since=10");
  });

  it("closes the stream and clears the timer when it goes away", () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );

    unmount();

    expect(streams[0].closed).toBe(true);
    // And nothing reconnects afterwards.
    act(() => void vi.advanceTimersByTime(5000));
    expect(streams).toHaveLength(1);
  });

  it("a stream that breaks after unmount does not reopen", () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() =>
      useNotificationStream({ enabled: true, since: 0, onNotification: vi.fn() }),
    );
    const stream = streams[0];

    unmount();
    act(() => stream.onerror?.());
    act(() => void vi.advanceTimersByTime(5000));

    expect(streams).toHaveLength(1);
    expect(polls).not.toHaveBeenCalled();
  });

  it("always calls the newest callback, not the one it opened with", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ onNotification }: { onNotification: (n: Notification) => void }) =>
        useNotificationStream({ enabled: true, since: 0, onNotification }),
      { initialProps: { onNotification: first } },
    );

    rerender({ onNotification: second });
    act(() => deliver(notification(1)));

    // Held in a ref, so reconnecting does not depend on render timing — and a
    // re-render does not tear the stream down either.
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
    expect(streams).toHaveLength(1);
  });
});
