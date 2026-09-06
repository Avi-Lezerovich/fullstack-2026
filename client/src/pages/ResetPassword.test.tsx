import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ResetPassword from "./ResetPassword";
import * as api from "../api";

/**
 * The page that used to take a new password twice before admitting the link
 * was dead.
 *
 * The reset token expires after RESET_TTL_MINUTES and can be spent exactly
 * once, but this page only ever checked that a `token=` was present in the
 * URL — so an expired, spent or invented link rendered the full form and only
 * failed on submit. Every assertion here is about the form not existing until
 * the server has said the link is live.
 *
 * src/pages/ is otherwise deliberately untested (see TESTING.md); this is
 * behaviour, not markup, which is why it earns a file.
 */

vi.mock("../api");

const draw = (search: string) =>
  render(
    <MemoryRouter initialEntries={[`/reset-password${search}`]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/forgot-password" element={<div>בקשת קישור</div>} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ResetPassword", () => {
  it("draws the form once the server says the link is live", async () => {
    vi.mocked(api.validatePasswordReset).mockResolvedValue({ ok: true });

    draw("?token=live-token");

    expect(await screen.findByTestId("reset-password")).toBeInTheDocument();
    expect(api.validatePasswordReset).toHaveBeenCalledWith("live-token");
  });

  it("shows the expired notice instead of a form for a dead link", async () => {
    // Expired, already spent and invented all arrive here as the same
    // rejection, because the server answers all three identically.
    vi.mocked(api.validatePasswordReset).mockRejectedValue(
      new Error("קישור האיפוס אינו תקף או שכבר נעשה בו שימוש."),
    );

    draw("?token=expired-token");

    expect(await screen.findByTestId("error-page")).toHaveAttribute("data-code", "410");
    expect(screen.queryByTestId("reset-password")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reset-submit")).not.toBeInTheDocument();
  });

  it("points a stranded user at a fresh link", async () => {
    vi.mocked(api.validatePasswordReset).mockRejectedValue(new Error("dead"));

    draw("?token=expired-token");

    expect(await screen.findByTestId("reset-request-new")).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("decides nothing while the check is still in flight", async () => {
    let resolve!: (value: { ok: true }) => void;
    vi.mocked(api.validatePasswordReset).mockReturnValue(
      new Promise((res) => {
        resolve = res;
      }),
    );

    draw("?token=live-token");

    expect(screen.getByText("בודק את הקישור…")).toBeInTheDocument();
    expect(screen.queryByTestId("reset-password")).not.toBeInTheDocument();
    expect(screen.queryByTestId("error-page")).not.toBeInTheDocument();

    resolve({ ok: true });

    await waitFor(() => expect(screen.getByTestId("reset-password")).toBeInTheDocument());
  });

  it("does not ask the server about a URL with no token in it", async () => {
    draw("");

    expect(await screen.findByTestId("error-page")).toHaveAttribute("data-code", "410");
    expect(api.validatePasswordReset).not.toHaveBeenCalled();
  });
});
