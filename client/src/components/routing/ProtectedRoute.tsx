import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { isLoggedIn } from "../../api";

/**
 * Wraps a route that requires a logged-in user.
 * If no token is in localStorage, redirects to /login.
 */
const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const location = useLocation();
  if (!isLoggedIn()) {
    // Stash the attempted destination so login could route back (future enhancement).
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
};
export default ProtectedRoute;
