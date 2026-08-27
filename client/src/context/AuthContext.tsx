import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import * as api from "../api";
import type { CurrentUser } from "../types";

/**
 * Who is signed in, in one place.
 *
 * The session itself is an httpOnly cookie the JavaScript cannot read, so the
 * only way to know the current user is to ask the server. This provider does
 * that once on mount and then keeps the answer.
 *
 * The previous version instead mirrored the user into localStorage and
 * broadcast a custom window event to keep components in sync — which meant
 * every component re-read localStorage, and the mirror could disagree with the
 * real cookie. A context is both simpler and can't drift.
 */
interface AuthState {
  user: CurrentUser | null;
  /** True until the initial /auth/me has settled — render nothing decisive before then. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<CurrentUser>;
  register: (name: string, email: string, password: string) => Promise<CurrentUser>;
  signOut: () => Promise<void>;
  setUser: (user: CurrentUser | null) => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const { user: me } = await api.fetchMe();
      setUser(me);
    } catch {
      // A failed probe means "not signed in" as far as the UI is concerned.
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signIn = useCallback(async (email: string, password: string) => {
    const { user: me } = await api.login(email, password);
    setUser(me);
    return me;
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const { user: me } = await api.signup(name, email, password);
    setUser(me);
    return me;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      // Even if the call failed, the local view must not keep claiming a session.
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn, register, signOut, setUser }),
    [user, loading, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider");
  return context;
}
