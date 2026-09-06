import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProtectedRoute from "./ProtectedRoute";
import { AuthProvider } from "../../context/AuthContext";
import * as api from "../../api";
import type { CurrentUser } from "../../types";

/**
 * The route guard, and the one line in it that is not obvious.
 *
 * `if (loading) return <Loading />` is what stops a signed-in user being
 * bounced to the login page for the split second before /auth/me answers. The
 * session cookie is httpOnly, so there is no synchronous way to know who is
 * reading - which means the guard is ALWAYS undecided for a moment, and
 * skipping that branch would log out every user on every page load.
 *
 * The refusal itself is a page rather than a redirect, so a visitor is told
 * why the door did not open. What must survive that change is `from`: the
 * login button still carries where they were going, which is what
 * Login.tsx sends them back to.
 */

vi.mock("../../api");

const user = { id: 1, name: "דנה", email: "dana@lolsuit.test" } as CurrentUser;

/** Stands in for Login.tsx, which reads `from` out of the router state. */
const LoginStub = () => {
  const { state } = useLocation();
  return (
    <div>
      עמוד ההתחברות
      <span data-testid="from">{(state as { from?: string })?.from ?? ""}</span>
    </div>
  );
};

const draw = () =>
  render(
    <MemoryRouter initialEntries={["/secret"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginStub />} />
          <Route
            path="/secret"
            element={
              <ProtectedRoute>
                <div>התוכן המוגן</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ProtectedRoute", () => {
  it("renders the page to somebody who is signed in", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user });

    draw();

    expect(await screen.findByText("התוכן המוגן")).toBeInTheDocument();
  });

  it("tells an anonymous visitor why the page did not open", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user: null });

    draw();

    expect(await screen.findByTestId("error-page")).toHaveAttribute("data-code", "401");
    expect(screen.queryByText("התוכן המוגן")).not.toBeInTheDocument();
  });

  it("offers the way in, still carrying where they were going", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user: null });

    draw();

    await userEvent.click(await screen.findByTestId("error-page-login"));

    // The regression this pins: a login button that dropped `from` would land
    // everyone on the feed after signing in, however they arrived.
    expect(await screen.findByText("עמוד ההתחברות")).toBeInTheDocument();
    expect(screen.getByTestId("from")).toHaveTextContent("/secret");
  });

  it("decides nothing until the session probe has answered", async () => {
    // The regression this branch prevents: without it, every signed-in user
    // is redirected to /login on every page load and only bounced back once
    // /auth/me returns.
    let resolve!: (value: { user: CurrentUser | null }) => void;
    vi.mocked(api.fetchMe).mockReturnValue(
      new Promise((res) => {
        resolve = res;
      }),
    );

    draw();

    expect(screen.queryByTestId("error-page")).not.toBeInTheDocument();
    expect(screen.queryByText("התוכן המוגן")).not.toBeInTheDocument();

    resolve({ user });

    await waitFor(() => expect(screen.getByText("התוכן המוגן")).toBeInTheDocument());
  });

  it("a failed probe is treated as signed out rather than as an outage", async () => {
    vi.mocked(api.fetchMe).mockRejectedValue(new Error("offline"));

    draw();

    expect(await screen.findByTestId("error-page")).toHaveAttribute("data-code", "401");
  });
});
