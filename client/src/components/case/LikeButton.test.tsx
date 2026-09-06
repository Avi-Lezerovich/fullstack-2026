import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LikeButton from "./LikeButton";
import * as api from "../../api";

/**
 * The guarded prop-sync, which is the whole reason this component has state.
 *
 * The case page refetches every ten seconds while a trial is live, so the
 * props move underneath the button when somebody else likes the filing — and
 * `useState` reads its argument only on the first render. A sync is therefore
 * needed; the subtlety is when NOT to run it, and the component's own comment
 * names the version that failed:
 *
 *   Keying the effect on a `busy` flag instead looks equivalent and is not:
 *   `busy` going false is itself a change, so the effect re-ran the instant
 *   our own request finished and overwrote the server's fresh answer with the
 *   stale props the parent had not refetched yet. The like landed in the
 *   database and the button snapped straight back.
 *
 * #44 made that guard carry more weight, not less: the button now reports the
 * server's answer through `onChange`, and the feed hands those same values
 * straight back down as props. So the round trip has to be tested AS a round
 * trip — report, receive back, and stop — which is what most of this file is.
 */

vi.mock("../../api");

const like = () => screen.getByTestId("like-button");

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LikeButton", () => {
  it("renders the props it was given", () => {
    render(<LikeButton caseId={1} liked={false} count={3} />);

    expect(like()).toHaveAttribute("data-liked", "false");
    expect(like()).toHaveTextContent("לייק · 3");
  });

  it("says so when the viewer has already liked it", () => {
    render(<LikeButton caseId={1} liked count={4} />);

    expect(like()).toHaveAttribute("data-liked", "true");
    expect(like()).toHaveTextContent("אהבתי · 4");
  });

  it("shows the word alone where the count lives elsewhere", () => {
    render(<LikeButton caseId={1} liked={false} count={3} showCount={false} />);

    expect(like()).toHaveTextContent("לייק");
    expect(like()).not.toHaveTextContent("3");
  });

  it("takes the server's answer rather than incrementing its own", async () => {
    // The server owns the state, so the button cannot drift out of step by
    // guessing what the new value should be.
    vi.mocked(api.toggleLike).mockResolvedValue({ liked: true, like_count: 9 });
    render(<LikeButton caseId={7} liked={false} count={3} />);

    await userEvent.click(like());

    expect(api.toggleLike).toHaveBeenCalledWith(7);
    await waitFor(() => expect(like()).toHaveTextContent("אהבתי · 9"));
  });

  it("reports the server's answer to its parent", async () => {
    vi.mocked(api.toggleLike).mockResolvedValue({ liked: true, like_count: 9 });
    const onChange = vi.fn();
    render(<LikeButton caseId={7} liked={false} count={3} onChange={onChange} />);

    await userEvent.click(like());

    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ liked: true, like_count: 9 }));
  });

  it("adopts what the parent hands back once, and then stops", async () => {
    // The #44 round trip: onChange -> the feed patches its row -> the same
    // values arrive back as props. The guard compares against the last props
    // it SAW, so this settles instead of oscillating.
    vi.mocked(api.toggleLike).mockResolvedValue({ liked: true, like_count: 9 });
    const { rerender } = render(<LikeButton caseId={7} liked={false} count={3} />);

    await userEvent.click(like());
    await waitFor(() => expect(like()).toHaveTextContent("אהבתי · 9"));

    rerender(<LikeButton caseId={7} liked count={9} />);
    expect(like()).toHaveTextContent("אהבתי · 9");

    rerender(<LikeButton caseId={7} liked count={9} />);
    expect(like()).toHaveTextContent("אהבתי · 9");
  });

  it("keeps the server's answer when stale props arrive afterwards", async () => {
    // The regression itself. The parent has not refetched, so it re-renders
    // with the values it was built with — and the button must not believe them.
    vi.mocked(api.toggleLike).mockResolvedValue({ liked: true, like_count: 9 });
    const { rerender } = render(<LikeButton caseId={7} liked={false} count={3} />);

    await userEvent.click(like());
    await waitFor(() => expect(like()).toHaveTextContent("אהבתי · 9"));

    rerender(<LikeButton caseId={7} liked={false} count={3} />);

    expect(like()).toHaveTextContent("אהבתי · 9");
    expect(like()).toHaveAttribute("data-liked", "true");
  });

  it("does adopt genuinely new props, so a poll is not ignored", async () => {
    // The other half: somebody else liked it, the page refetched, and the
    // number really did change. A guard that never synced would be as wrong as
    // one that always did.
    const { rerender } = render(<LikeButton caseId={7} liked={false} count={3} />);

    rerender(<LikeButton caseId={7} liked={false} count={12} />);

    expect(like()).toHaveTextContent("לייק · 12");
  });

  it("leaves the previous state visible when the toggle fails", async () => {
    // An optimistic flip here would claim something untrue.
    vi.mocked(api.toggleLike).mockRejectedValue(new Error("נדרשת התחברות."));
    const onChange = vi.fn();
    render(<LikeButton caseId={7} liked={false} count={3} onChange={onChange} />);

    await userEvent.click(like());

    await waitFor(() => expect(like()).toBeEnabled());
    expect(like()).toHaveTextContent("לייק · 3");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("cannot be clicked twice while a request is in flight", async () => {
    let resolve!: (value: { liked: boolean; like_count: number }) => void;
    vi.mocked(api.toggleLike).mockReturnValue(
      new Promise((res) => {
        resolve = res;
      }),
    );
    render(<LikeButton caseId={7} liked={false} count={3} />);

    await userEvent.click(like());

    expect(like()).toBeDisabled();
    resolve({ liked: true, like_count: 4 });
    await waitFor(() => expect(like()).toBeEnabled());
    expect(api.toggleLike).toHaveBeenCalledTimes(1);
  });

  it("is inert when the parent disables it", async () => {
    // The feed renders the footer signed out as well, disabled rather than
    // hidden, because the counts are public and hiding the buttons would take
    // the numbers with them.
    render(<LikeButton caseId={7} liked={false} count={3} disabled />);

    expect(like()).toBeDisabled();
    await userEvent.click(like(), { pointerEventsCheck: 0 });
    expect(api.toggleLike).not.toHaveBeenCalled();
  });
});
