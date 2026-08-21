import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../../context/AuthContext";
import { Loading } from "../common/StateViews";

/**
 * Gate a route behind a session.
 *
 * The `loading` check is what stops a signed-in user being bounced to the
 * login page for the split second before /auth/me answers — the cookie is
 * httpOnly, so there is no synchronous way to know who they are.
 */
const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}; export default ProtectedRoute;
