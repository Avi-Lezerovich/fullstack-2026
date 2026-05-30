import { useState, useEffect } from "react";
import { getStoredUser } from "../api";
import type { User } from "../types";

/**
 * Returns the currently logged-in user (or null) and keeps it in sync with
 * login/logout events across the whole app.
 *
 * Two event sources are subscribed:
 *   - "auth-change" (custom event dispatched by saveSession/clearSession in api.ts)
 *     → same-tab updates after login or logout.
 *   - "storage" (browser-native event)
 *     → cross-tab sync; if the user logs out in another tab, this tab updates too.
 */
export const useCurrentUser = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(getStoredUser());

  useEffect(() => {
    const refresh = () => setCurrentUser(getStoredUser());
    window.addEventListener("auth-change", refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("auth-change", refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  return currentUser;
};
