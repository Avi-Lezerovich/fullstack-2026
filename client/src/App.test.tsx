import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import * as api from "./api";
import { AuthProvider } from "./context/AuthContext";
import { NotificationProvider } from "./context/NotificationContext";

/**
 * The routing table's last line.
 *
 * `path="*"` used to be `<Navigate to="/" replace />`, which made a mistyped
 * address indistinguishable from having asked for the feed — the reader got a
 * working page and no hint that the one they wanted does not exist. This is the
 * whole reason the route exists, so it is asserted through the real App rather
 * than through a stand-in routing table that could drift from it.
 *
 * Signed out on purpose: the notification stream only opens for a signed-in
 * user, so nothing here reaches for an EventSource.
 */

vi.mock("./api");

const draw = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <NotificationProvider>
          <App />
        </NotificationProvider>
      </AuthProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchMe).mockResolvedValue({ user: null });
  vi.mocked(api.fetchCases).mockResolvedValue({ cases: [], total: 0, limit: 10, offset: 0 });
});

describe("App routing", () => {
  it("answers an unknown address with the 404 page, not with the feed", async () => {
    draw("/no-such-docket");

    expect(await screen.findByTestId("error-page")).toHaveAttribute("data-code", "404");
    expect(api.fetchCases).not.toHaveBeenCalled();
  });

  it("offers the way back from it", async () => {
    draw("/no-such-docket");

    expect(await screen.findByRole("link", { name: "חזרה לאולם הראשי" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("still routes a real address to its page", async () => {
    draw("/login");

    expect(await screen.findByTestId("login-submit")).toBeInTheDocument();
    expect(screen.queryByTestId("error-page")).not.toBeInTheDocument();
  });
});
