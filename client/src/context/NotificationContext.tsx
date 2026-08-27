import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import * as api from "../api";
import { useAuth } from "./AuthContext";
import { useNotificationStream } from "../hooks/useNotificationStream";
import type { Notification } from "../types";

/**
 * Every notification in the app, in one place.
 *
 * There is exactly ONE of these, mounted at the root. That is the whole point:
 * the stream is a real network connection and the unread counter is real
 * state, so a second copy would open a second EventSource against the same
 * user and count every row twice. The bell, the inbox badge and the Messages
 * page all read from here.
 */
interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  markRead: (ids?: number[]) => Promise<void>;
  refresh: () => Promise<void>;
  /**
   * Id of the newest `message` notification seen so far. It changes exactly
   * once per incoming DM, which is what <MessagesLink> and the Messages page
   * watch to know their view is stale.
   */
  latestMessageId: number;
}

const NotificationContext = createContext<NotificationState | undefined>(undefined);

const MAX_KEPT = 40;

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [cursor, setCursor] = useState(0);
  /**
   * False until the initial history has landed and set the cursor. The stream
   * must not connect before then: at `since=0` the server replays the user's
   * entire notification history, and every row arrives looking new.
   */
  const [loaded, setLoaded] = useState(false);

  /**
   * Every notification id this session has already accounted for.
   *
   * The list could dedupe itself by scanning its own state, but the unread
   * counter cannot — and the two must agree. A REST refresh and a stream frame
   * routinely deliver the same row (the refresh is a snapshot, the stream is a
   * tail, and they overlap), which counted that row twice until this existed.
   */
  const seen = useRef<Set<number>>(new Set());

  const refresh = useCallback(async () => {
    if (!user) {
      setNotifications([]);
      setUnreadCount(0);
      setCursor(0);
      setLoaded(false);
      seen.current.clear();
      return;
    }
    try {
      const body = await api.fetchNotifications();
      setNotifications(body.notifications);
      setUnreadCount(body.unread_count);
      setCursor(body.latest_id);
      for (const notification of body.notifications) seen.current.add(notification.id);
    } catch {
      // Leave whatever is on screen rather than blanking the bell.
    } finally {
      // Even a failed history load has to release the stream, or a signed-in
      // user whose first request failed would never receive anything live.
      if (user) setLoaded(true);
    }
  }, [user]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /**
   * One handler for both transports. The stream and the polling fallback both
   * land here, which is why the bell has no idea which one is running.
   */
  const receive = useCallback((incoming: Notification) => {
    if (seen.current.has(incoming.id)) return;
    seen.current.add(incoming.id);

    setNotifications((current) => [incoming, ...current].slice(0, MAX_KEPT));
    if (!incoming.is_read) setUnreadCount((count) => count + 1);
  }, []);

  useNotificationStream({
    enabled: Boolean(user) && loaded,
    since: cursor,
    onNotification: receive,
  });

  const markRead = useCallback(async (ids?: number[]) => {
    try {
      const body = await api.markNotificationsRead(ids);
      setUnreadCount(body.unread_count);
      setNotifications((current) =>
        current.map((n) => (!ids || ids.includes(n.id) ? { ...n, is_read: true } : n)),
      );
    } catch {
      // Nothing useful to say; the count corrects itself on the next refresh.
    }
  }, []);

  const latestMessageId = notifications.find((n) => n.type === "message")?.id ?? 0;

  const value = useMemo(
    () => ({ notifications, unreadCount, markRead, refresh, latestMessageId }),
    [notifications, unreadCount, markRead, refresh, latestMessageId],
  );

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>;
}

export function useNotifications(): NotificationState {
  const context = useContext(NotificationContext);
  if (!context) throw new Error("useNotifications must be used inside a NotificationProvider");
  return context;
}
