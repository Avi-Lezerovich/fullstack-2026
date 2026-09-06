import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./AuthContext";
import * as api from "../api";
import type { CurrentUser } from "../types";

/**
 * Who is signed in.
 *
 * The session is an httpOnly cookie the JavaScript cannot read, so the only
 * way to know the current user is to ask the server — which makes `loading`
 * load-bearing rather than cosmetic. Every route guard in the app reads it,
 * and rendering a decision before /auth/me settles is how a signed-in user
 * gets bounced to the login page for a split second.
 *
 * The api module is mocked rather than fetch, because that is the boundary
 * this provider actually owns: it calls four functions and stores what they
 * return.
 */

vi.mock("../api");

const user = { id: 1, name: "דנה", email: "dana@lolsuit.test" } as CurrentUser;

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

beforeEach(() => {
  // `vi.mock` hoists one mock per module for the whole file, so call counts
  // carry over between tests unless they are reset — and several assertions
  // below are about how MANY times /auth/me was asked.
  vi.clearAllMocks();
  vi.mocked(api.fetchMe).mockResolvedValue({ user: null });
  vi.mocked(api.login).mockResolvedValue({ user });
  vi.mocked(api.signup).mockResolvedValue({ user });
  vi.mocked(api.logout).mockResolvedValue({ ok: true });
});

describe("AuthProvider", () => {
  it("asks the server once on mount and keeps the answer", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user });

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.fetchMe).toHaveBeenCalledTimes(1);
    expect(result.current.user).toEqual(user);
  });

  it("is loading until that first answer settles", async () => {
    let resolve!: (value: { user: CurrentUser | null }) => void;
    vi.mocked(api.fetchMe).mockReturnValue(
      new Promise((res) => {
        resolve = res;
      }),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    // Nothing decisive may render before this flips.
    expect(result.current.loading).toBe(true);
    expect(result.current.user).toBeNull();

    await act(async () => {
      resolve({ user });
    });
    expect(result.current.loading).toBe(false);
  });

  it("treats a failed probe as anonymous rather than as an error", async () => {
    // There is nowhere to show an error here, and "not signed in" is what the
    // UI needs to know either way.
    vi.mocked(api.fetchMe).mockRejectedValue(new Error("offline"));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it("signing in stores the user the server returned", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.signIn("dana@lolsuit.test", "correct-horse");
    });

    expect(api.login).toHaveBeenCalledWith("dana@lolsuit.test", "correct-horse");
    expect(result.current.user).toEqual(user);
  });

  it("a failed sign-in leaves the viewer signed out and rethrows", async () => {
    // The form shows the message, so the error has to reach it.
    vi.mocked(api.login).mockRejectedValue(new Error("כתובת האימייל או הסיסמה שגויות."));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await expect(
      act(async () => {
        await result.current.signIn("dana@lolsuit.test", "wrong");
      }),
    ).rejects.toThrow("כתובת האימייל או הסיסמה שגויות.");

    expect(result.current.user).toBeNull();
  });

  it("registering signs you straight in", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.register("דנה", "dana@lolsuit.test", "correct-horse");
    });

    expect(api.signup).toHaveBeenCalledWith("דנה", "dana@lolsuit.test", "correct-horse");
    expect(result.current.user).toEqual(user);
  });

  it("signing out clears the user", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).toEqual(user));

    await act(async () => {
      await result.current.signOut();
    });

    expect(result.current.user).toBeNull();
  });

  it("signing out clears the user even when the request fails", async () => {
    // The local view must not keep claiming a session it may no longer have —
    // which is why the clear is in a `finally`.
    vi.mocked(api.fetchMe).mockResolvedValue({ user });
    vi.mocked(api.logout).mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).toEqual(user));

    await act(async () => {
      await result.current.signOut().catch(() => {});
    });

    expect(result.current.user).toBeNull();
  });

  it("exposes setUser so a profile edit updates the header without a refetch", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.user).toEqual(user));

    act(() => result.current.setUser({ ...user, name: "דנה החדשה" }));

    expect(result.current.user?.name).toBe("דנה החדשה");
    expect(api.fetchMe).toHaveBeenCalledTimes(1);
  });

  it("keeps one identity for the value while nothing about it changed", async () => {
    // useMemo'd, so every consumer of the context does not re-render on each
    // render of the provider's parent.
    vi.mocked(api.fetchMe).mockResolvedValue({ user });
    const { result, rerender } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    const before = result.current;

    rerender();

    expect(result.current).toBe(before);
  });
});

describe("useAuth", () => {
  it("refuses to be used outside a provider", () => {
    // A component reading a half-initialised context would silently render as
    // though nobody were signed in, which is the worst possible failure here.
    const Orphan = () => {
      useAuth();
      return null;
    };

    const noise = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow("useAuth must be used inside an AuthProvider");
    noise.mockRestore();
  });

  it("gives every consumer under one provider the same answer", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue({ user });

    const Name = () => <span>{useAuth().user?.name ?? "אנונימי"}</span>;

    render(
      <AuthProvider>
        <Name />
        <Name />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getAllByText("דנה")).toHaveLength(2));
    expect(api.fetchMe).toHaveBeenCalledTimes(1);
  });
});
