import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppErrorBoundary from "./AppErrorBoundary";

/**
 * The boundary, and the reset that is easy to forget.
 *
 * React gives no way to un-catch an error, so a boundary that has caught keeps
 * showing the crash page forever — including after the user has navigated to a
 * page that works. Without the pathname key, one broken case page would look
 * like a broken site until a full reload.
 *
 * React logs every caught error itself, so console.error is silenced here to
 * keep the run readable; the assertion that our own handler ran is separate.
 */

const Bomb = () => {
  throw new Error("הדיון קרס");
};

let logged: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  logged = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  logged.mockRestore();
});

describe("AppErrorBoundary", () => {
  it("replaces a crashed page with the branded 500 page", () => {
    render(
      <MemoryRouter>
        <AppErrorBoundary>
          <Bomb />
        </AppErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("error-page")).toHaveAttribute("data-code", "500");
    expect(screen.getByText("התקלה נרשמה בפרוטוקול")).toBeInTheDocument();
  });

  it("reports the crash rather than swallowing it", () => {
    render(
      <MemoryRouter>
        <AppErrorBoundary>
          <Bomb />
        </AppErrorBoundary>
      </MemoryRouter>,
    );

    expect(logged).toHaveBeenCalledWith(
      "Unhandled render error",
      expect.objectContaining({ message: "הדיון קרס" }),
      expect.anything(),
    );
  });

  it("clears itself when the reader navigates somewhere else", async () => {
    render(
      <MemoryRouter initialEntries={["/broken"]}>
        <AppErrorBoundary>
          <Routes>
            <Route path="/broken" element={<Bomb />} />
            <Route path="/" element={<div>אולם המשפט</div>} />
          </Routes>
        </AppErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("error-page")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("link", { name: "חזרה לאולם הראשי" }));

    expect(await screen.findByText("אולם המשפט")).toBeInTheDocument();
    expect(screen.queryByTestId("error-page")).not.toBeInTheDocument();
  });

  it("stays out of the way when nothing throws", () => {
    render(
      <MemoryRouter>
        <AppErrorBoundary>
          <div>הדיון מתנהל</div>
        </AppErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText("הדיון מתנהל")).toBeInTheDocument();
    expect(screen.queryByTestId("error-page")).not.toBeInTheDocument();
  });
});
