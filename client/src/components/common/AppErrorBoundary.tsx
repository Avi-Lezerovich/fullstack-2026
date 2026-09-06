import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";

import { ErrorPage } from "./ErrorPage";

/**
 * The last line before a white screen.
 *
 * A render that throws takes the whole tree with it, and React offers exactly
 * one way to catch that — a class component. This app builds its routes with
 * `<BrowserRouter>` + `<Routes>` rather than `createBrowserRouter`, so the
 * router's own `errorElement` is not available to us.
 *
 * The `resetKey` is the part that is easy to leave out: a boundary that has
 * caught stays caught, so without it one crashed page would keep showing the
 * crash page after the user navigated somewhere healthy. Keying it on the path
 * means moving away is the retry.
 */

class Boundary extends Component<
  { children: ReactNode; resetKey: string },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Swallowing it here would hide the stack from the console in development
    // and from anything watching the browser in production.
    console.error("Unhandled render error", error, info.componentStack);
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <ErrorPage
        code="500"
        title="התקלה נרשמה בפרוטוקול"
        description="משהו קרס באמצע הדיון והדף לא הצליח להיטען. אפשר לרענן ולנסות שוב."
        action={
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="center">
            <Button variant="contained" onClick={() => window.location.reload()}>
              רענון הדף
            </Button>
            <Button component={RouterLink} to="/">
              חזרה לאולם הראשי
            </Button>
          </Stack>
        }
      />
    );
  }
}

const AppErrorBoundary = ({ children }: { children: ReactNode }) => {
  const location = useLocation();
  return <Boundary resetKey={location.pathname}>{children}</Boundary>;
}; export default AppErrorBoundary;
