import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FollowButton from "./FollowButton";
import * as api from "../../api";

/**
 * The same guarded prop-sync as LikeButton, and it is worth testing twice.
 *
 * The two components share a shape and not a line of code, so the guard is
 * implemented separately in each and can regress separately in each. The
 * comment in FollowButton points at LikeButton "for the long version", which
 * is exactly the arrangement where one of the two quietly stops matching.
 *
 * The labels get their own test for a different reason. #44 changed them from
 * "עוקב"/"עקוב", which address a man, to the pair the rest of the app uses —
 * and a button is the one control here that tells a reader what they are and
 * what to do. Queried by accessible name so reverting that is a failure rather
 * than a silent regression.
 */

vi.mock("../../api");

const follow = () => screen.getByTestId("follow-button");

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FollowButton", () => {
  it("addresses a reader it has not asked in both genders", () => {
    // The unpressed label is an imperative, so it takes the imperative pair
    // rather than a second copy of the participle one.
    const { rerender } = render(<FollowButton caseId={1} following={false} count={2} />);
    expect(screen.getByRole("button", { name: /עקוב\/עקבי/ })).toBeInTheDocument();

    rerender(<FollowButton caseId={1} following count={2} />);
    expect(screen.getByRole("button", { name: /עוקב\/ת/ })).toBeInTheDocument();
  });

  it("renders the props it was given", () => {
    render(<FollowButton caseId={1} following count={2} />);

    expect(follow()).toHaveAttribute("data-following", "true");
    expect(follow()).toHaveAttribute("data-follow-count", "2");
    expect(follow()).toHaveTextContent("עוקב/ת · 2");
  });

  it("shows the word alone where the count lives elsewhere", () => {
    render(<FollowButton caseId={1} following={false} count={2} showCount={false} />);

    expect(follow()).toHaveTextContent("עקוב/עקבי");
    expect(follow()).not.toHaveTextContent("2");
  });

  it("takes the server's answer rather than incrementing its own", async () => {
    vi.mocked(api.toggleFollow).mockResolvedValue({ following: true, follow_count: 6 });
    render(<FollowButton caseId={4} following={false} count={2} />);

    await userEvent.click(follow());

    expect(api.toggleFollow).toHaveBeenCalledWith(4);
    await waitFor(() => expect(follow()).toHaveTextContent("עוקב/ת · 6"));
  });

  it("reports the server's answer to its parent", async () => {
    vi.mocked(api.toggleFollow).mockResolvedValue({ following: true, follow_count: 6 });
    const onChange = vi.fn();
    render(<FollowButton caseId={4} following={false} count={2} onChange={onChange} />);

    await userEvent.click(follow());

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ following: true, follow_count: 6 }),
    );
  });

  it("adopts what the parent hands back once, and then stops", async () => {
    vi.mocked(api.toggleFollow).mockResolvedValue({ following: true, follow_count: 6 });
    const { rerender } = render(<FollowButton caseId={4} following={false} count={2} />);

    await userEvent.click(follow());
    await waitFor(() => expect(follow()).toHaveTextContent("עוקב/ת · 6"));

    rerender(<FollowButton caseId={4} following count={6} />);
    rerender(<FollowButton caseId={4} following count={6} />);

    expect(follow()).toHaveTextContent("עוקב/ת · 6");
  });

  it("keeps the server's answer when stale props arrive afterwards", async () => {
    vi.mocked(api.toggleFollow).mockResolvedValue({ following: true, follow_count: 6 });
    const { rerender } = render(<FollowButton caseId={4} following={false} count={2} />);

    await userEvent.click(follow());
    await waitFor(() => expect(follow()).toHaveTextContent("עוקב/ת · 6"));

    rerender(<FollowButton caseId={4} following={false} count={2} />);

    expect(follow()).toHaveAttribute("data-following", "true");
    expect(follow()).toHaveTextContent("עוקב/ת · 6");
  });

  it("does adopt genuinely new props", async () => {
    const { rerender } = render(<FollowButton caseId={4} following={false} count={2} />);

    rerender(<FollowButton caseId={4} following={false} count={11} />);

    expect(follow()).toHaveTextContent("עקוב/עקבי · 11");
  });

  it("leaves the previous state visible when the toggle fails", async () => {
    vi.mocked(api.toggleFollow).mockRejectedValue(new Error("התיק המבוקש לא נמצא."));
    const onChange = vi.fn();
    render(<FollowButton caseId={4} following={false} count={2} onChange={onChange} />);

    await userEvent.click(follow());

    await waitFor(() => expect(follow()).toBeEnabled());
    expect(follow()).toHaveTextContent("עקוב/עקבי · 2");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("cannot be clicked twice while a request is in flight", async () => {
    let resolve!: (value: { following: boolean; follow_count: number }) => void;
    vi.mocked(api.toggleFollow).mockReturnValue(
      new Promise((res) => {
        resolve = res;
      }),
    );
    render(<FollowButton caseId={4} following={false} count={2} />);

    await userEvent.click(follow());

    expect(follow()).toBeDisabled();
    resolve({ following: true, follow_count: 3 });
    await waitFor(() => expect(follow()).toBeEnabled());
    expect(api.toggleFollow).toHaveBeenCalledTimes(1);
  });

  it("is inert when the parent disables it", async () => {
    render(<FollowButton caseId={4} following={false} count={2} disabled />);

    expect(follow()).toBeDisabled();
    await userEvent.click(follow(), { pointerEventsCheck: 0 });
    expect(api.toggleFollow).not.toHaveBeenCalled();
  });
});
