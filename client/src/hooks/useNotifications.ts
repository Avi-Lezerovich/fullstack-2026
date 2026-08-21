import { useCallback, useEffect, useRef, useState } from "react";

import { fetchNotifications, markNotificationsRead } from "../api";
import type { Notification } from "../types";

const POLL_INTERVAL_MS = 10_000;
/** Two failures inside this window means SSE is not working here. */
const FAILURE_WINDOW_MS = 30_000;
const FAILURE_LIMIT = 2;

interface Options {
  enabled: boolean;
  /** Where to resume from. Both transports use the same cursor. */
  since: number;
  onNotification: (notification: Notification) => void;
}

/**
 * Live notifications, over SSE where it works and polling where it does not.
 *
 * Both transports call the identical `onNotification` callback and advance the
 * same `notifications.id` cursor, so every consumer is transport-agnostic —
 * which is exactly why the polling path could ship first and SSE could be
 * layered on afterwards without touching the bell.
 *
 * Falling back is permanent for the session rather than retried forever: if a
 * proxy is buffering event streams, reconnecting will not fix it, and a
 * reconnect loop is worse than polling.
 */
export function useNotificationStream({ enabled, since, onNotification }: Options) {
  // Held in refs so reconnecting does not depend on render timing.
  const cursor = useRef(since);
  const handler = useRef(onNotification);
  handler.current = onNotification;

  useEffect(() => {
    cursor.current = Math.max(cursor.current, since);
  }, [since]);

  useEffect(() => {
    if (!enabled) return;

    let stopped = false;
    let source: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let failures: number[] = [];

    const poll = async () => {
      try {
        const response = await fetch(`/api/notifications?since=${cursor.current}`, {
          credentials: "include",
        });
        if (!response.ok) return;
        const body = (await response.json()) as { notifications: Notification[] };
        for (const notification of body.notifications) {
          cursor.current = Math.max(cursor.current, notification.id);
          handler.current(notification);
        }
      } catch {
        // A failed poll is not worth surfacing; the next one may succeed.
      }
    };

    const startPolling = () => {
      if (pollTimer || stopped) return;
      void poll();
      pollTimer = setInterval(() => void poll(), POLL_INTERVAL_MS);
    };

    const connect = () => {
      if (stopped) return;
      if (typeof EventSource === "undefined") {
        startPolling();
        return;
      }

      source = new EventSource(`/api/notifications/stream?since=${cursor.current}`);

      source.addEventListener("notification", (event) => {
        try {
          const notification = JSON.parse((event as MessageEvent).data) as Notification;
          cursor.current = Math.max(cursor.current, notification.id);
          handler.current(notification);
        } catch {
          // Ignore a frame we cannot parse rather than tearing down the stream.
        }
      });

      source.onerror = () => {
        source?.close();
        source = null;
        if (stopped) return;

        const now = Date.now();
        failures = [...failures, now].filter((at) => now - at < FAILURE_WINDOW_MS);

        if (failures.length >= FAILURE_LIMIT) {
          // SSE is not viable here. Polling from now on.
          startPolling();
        } else {
          // The server caps each stream's lifetime, so a clean close is the
          // normal case rather than an error — reconnect promptly.
          setTimeout(connect, 1000);
        }
      };
    };

    connect();

    return () => {
      stopped = true;
      source?.close();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [enabled]);
}

/** How many rows the bell's dropdown keeps in memory. */
const MAX_ROWS = 50;

export interface NotificationsState {
  notifications: Notification[];
  unreadCount: number;
  /** Marks the given ids read, or every notification when called with no args. */
  markRead: (ids?: number[]) => Promise<void>;
  /**
   * Id of the newest `message` notification seen so far. It changes exactly
   * once per incoming DM, which is what <MessagesLink> watches to know its
   * unread badge is stale.
   */
  latestMessageId: number;
}

/**
 * The notification feed as state: a history fetched once on sign-in, kept
 * current by `useNotificationStream`.
 *
 * There is no notification provider in this app, so <TopBar> calls this once
 * and passes the result down to the bell and the inbox badge. Mounting it
 * twice would open two streams.
 *
 * `enabled` is false for logged-out visitors — the endpoint requires auth.
 */
export function useNotifications(enabled: boolean): NotificationsState {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [since, setSince] = useState(0);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setNotifications([]);
      setUnreadCount(0);
      setSince(0);
      setLoaded(false);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const data = await fetchNotifications();
        if (cancelled) return;
        setNotifications(data.notifications.slice(0, MAX_ROWS));
        setUnreadCount(data.unread_count);
        setSince(data.latest_id);
      } catch {
        // Start empty rather than blocking the app bar on a failed history
        // load; the stream still delivers anything that arrives from now on.
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const receive = useCallback((notification: Notification) => {
    // A reconnect can replay from the cursor, so drop anything already held.
    setNotifications((prev) =>
      prev.some((n) => n.id === notification.id)
        ? prev
        : [notification, ...prev].slice(0, MAX_ROWS),
    );
    if (!notification.is_read) setUnreadCount((count) => count + 1);
  }, []);

  // Held until the history load has set the cursor — connecting at since=0
  // would replay the whole table as if it were new.
  useNotificationStream({ enabled: enabled && loaded, since, onNotification: receive });

  const markRead = useCallback(async (ids?: number[]) => {
    try {
      const { unread_count } = await markNotificationsRead(ids);
      setUnreadCount(unread_count);
      setNotifications((prev) =>
        prev.map((n) => (!ids || ids.includes(n.id) ? { ...n, is_read: true } : n)),
      );
    } catch {
      // Leave the badge as-is rather than lying about it.
    }
  }, []);

  const latestMessageId = notifications.find((n) => n.type === "message")?.id ?? 0;

  return { notifications, unreadCount, markRead, latestMessageId };
}
