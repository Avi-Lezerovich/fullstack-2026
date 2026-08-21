import { useEffect, useState } from "react";

import { fetchMe } from "../api";
import type { CurrentUser } from "../types";

/**
 * Returns the currently signed-in user (or null) and keeps it in sync with
 * login/logout across the whole app.
 *
 * The session is an httpOnly cookie, so the client cannot read who is signed in
 * without asking: the identity comes from `/auth/me`, not from localStorage.
 * The answer is cached in a module-level variable so the second and third
 * component to call this hook render immediately instead of each firing their
 * own request.
 *
 * Two event sources are subscribed:
 *   - "auth-change" — dispatched by `signalAuthChange()` after login or logout
 *     → same-tab updates.
 *   - "storage" — browser-native
 *     → cross-tab sync; if the user logs out in another tab, this tab follows.
 */

let cachedUser: CurrentUser | null = null;
let inFlight: Promise<CurrentUser | null> | null = null;

/** One request at a time, shared by every hook instance that asks. */
const loadUser = (force = false): Promise<CurrentUser | null> => {
  if (force) {
    cachedUser = null;
    inFlight = null;
  }
  if (!inFlight) {
    inFlight = fetchMe()
      .then((response) => {
        cachedUser = response.user;
        return cachedUser;
      })
      .catch(() => {
        // A 401 is the normal answer for a signed-out visitor, not an error.
        cachedUser = null;
        return null;
      });
  }
  return inFlight;
};

/**
 * Tells every `useCurrentUser` in the app that the session changed.
 * Call it after a successful login, signup or logout.
 */
export const signalAuthChange = () => {
  window.dispatchEvent(new Event("auth-change"));
};

export const useCurrentUser = (): CurrentUser | null => {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(cachedUser);

  useEffect(() => {
    let cancelled = false;

    const refresh = (force = false) => {
      void loadUser(force).then((user) => {
        if (!cancelled) setCurrentUser(user);
      });
    };

    refresh();

    // A session change invalidates the cache, so these force a re-fetch.
    const onAuthChange = () => refresh(true);
    window.addEventListener("auth-change", onAuthChange);
    window.addEventListener("storage", onAuthChange);
    return () => {
      cancelled = true;
      window.removeEventListener("auth-change", onAuthChange);
      window.removeEventListener("storage", onAuthChange);
    };
  }, []);

  return currentUser;
};
