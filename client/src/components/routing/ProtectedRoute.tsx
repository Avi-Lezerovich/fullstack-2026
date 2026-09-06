import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import { useLocation } from "react-router-dom";
import { Link as RouterLink } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../../context/AuthContext";
import { ErrorPage } from "../common/ErrorPage";
import { Loading } from "../common/StateViews";

/**
 * Gate a route behind a session.
 *
 * The `loading` check is what stops a signed-in user being bounced to the
 * login page for the split second before /auth/me answers — the cookie is
 * httpOnly, so there is no synchronous way to know who they are.
 *
 * An anonymous visitor gets told why rather than being silently moved: the
 * refusal is a page, and the button on it still carries `from`, so signing in
 * lands them back where they were aiming.
 */
const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;

  if (!user) {
    return (
      <ErrorPage
        code="401"
        title="האולם סגור לקהל"
        description="רק בעלי דין רשומים רשאים לעבור את הדלת הזו. התחבר כדי להמשיך."
        action={
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="center">
            <Button
              component={RouterLink}
              to="/login"
              state={{ from: location.pathname }}
              variant="contained"
              data-testid="error-page-login"
            >
              כניסה
            </Button>
            <Button component={RouterLink} to="/">
              חזרה לאולם הראשי
            </Button>
          </Stack>
        }
      />
    );
  }

  return <>{children}</>;
}; export default ProtectedRoute;
