import { useEffect, useRef } from "react";

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
export const useNotificationStream = ({ enabled, since, onNotification }: Options) => {
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
}; 
