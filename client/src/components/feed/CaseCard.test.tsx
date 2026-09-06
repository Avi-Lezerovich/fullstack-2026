import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CaseCard from "./CaseCard";
import * as api from "../../api";
import type { Case } from "../../types";

/**
 * The feed card, and the footer #44 rebuilt.
 *
 * Two decisions there are worth pinning, and both are about what a signed-out
 * reader sees. The footer is **rendered disabled rather than hidden**, because
 * the counts on it are public and taking the row away with the buttons would
 * take the numbers with it. And the buttons sit **outside** the
 * `CardActionArea`: nested inside the link, every tap would navigate as well
 * as toggle.
 *
 * The third is the round trip. The card's stat row used to read the `case`
 * prop, so a like from the feed changed the button and left the number under
 * it at whatever the feed was fetched with - a like that visibly did nothing.
 * The button now reports the server's answer, the card passes it up, and the
 * list patches its own row. This tests the middle link of that chain.
 */

vi.mock("../../api");

const testCase = (over: Partial<Case> = {}): Case =>
  ({
    id: 3,
    title: "התביעה נגד יום שני",
    body: "יום שני התחיל בלי רשות ובלי התראה מוקדמת.",
    image_url: null,
    author: { id: 2, name: "דנה כהן", avatar_url: null, is_bot: false },
    defendant_text: "יום שני",
    defendant: null,
    charges: ["גרימת עוגמת נפש"],
    status: "witness_phase",
    phase_deadline_at: null,
    filed_at: "2026-09-06T10:00:00",
    verdict: null,
    sentence_text: null,
    verdict_at: null,
    closed_at: null,
    moderation_status: "published",
    created_at: "2026-09-06T10:00:00",
    like_count: 4,
    comment_count: 2,
    follow_count: 6,
    viewer_has_liked: false,
    viewer_is_following: false,
    last_activity_at: "2026-09-06T11:00:00",
    ...over,
  }) as Case;

const draw = (props: Partial<React.ComponentProps<typeof CaseCard>> = {}) =>
  render(
    <MemoryRouter>
      <CaseCard case={props.case ?? testCase()} {...props} />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CaseCard", () => {
  it("shows the filing and every count it publishes", () => {
    draw();

    expect(screen.getByText("התביעה נגד יום שני")).toBeInTheDocument();
    expect(screen.getByText("גרימת עוגמת נפש")).toBeInTheDocument();
    expect(screen.getByTestId("like-button")).toHaveTextContent("4");
    expect(screen.getByTestId("follow-button")).toHaveTextContent("6");
    expect(screen.getByTestId("card-comment-count")).toHaveTextContent("2");
  });

  it("truncates a long filing rather than printing the whole thing", () => {
    draw({ case: testCase({ body: "א".repeat(400) }) });

    expect(screen.getByText(/…$/)).toBeInTheDocument();
  });

  it("shows the footer to a signed-out reader, disabled rather than hidden", () => {
    // The counts are public. Hiding the row would hide them along with the
    // controls, which is what the old separate stat strip was carrying.
    draw({ canFollow: false });

    expect(screen.getByTestId("like-button")).toBeDisabled();
    expect(screen.getByTestId("follow-button")).toBeDisabled();
    expect(screen.getByTestId("like-button")).toHaveTextContent("4");
    expect(screen.getByTestId("follow-button")).toHaveTextContent("6");
  });

  it("enables both buttons for somebody who is signed in", () => {
    draw({ canFollow: true });

    expect(screen.getByTestId("like-button")).toBeEnabled();
    expect(screen.getByTestId("follow-button")).toBeEnabled();
  });

  it("passes a like straight up to the list that owns the row", async () => {
    // The card does not patch itself: the list owns the row, so the list
    // applies it. Without this the number under the button kept the value the
    // feed was fetched with until a reload.
    vi.mocked(api.toggleLike).mockResolvedValue({ liked: true, like_count: 5 });
    const onChange = vi.fn();
    draw({ canFollow: true, onChange });

    await userEvent.click(screen.getByTestId("like-button"));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ viewer_has_liked: true, like_count: 5 }),
    );
  });

  it("passes a follow up the same way", async () => {
    vi.mocked(api.toggleFollow).mockResolvedValue({ following: true, follow_count: 7 });
    const onChange = vi.fn();
    draw({ canFollow: true, onChange });

    await userEvent.click(screen.getByTestId("follow-button"));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ viewer_is_following: true, follow_count: 7 }),
    );
  });

  it("toggling does not also navigate to the case", async () => {
    // The buttons are outside the CardActionArea for exactly this reason.
    vi.mocked(api.toggleLike).mockResolvedValue({ liked: true, like_count: 5 });
    draw({ canFollow: true });

    await userEvent.click(screen.getByTestId("like-button"));

    // The link is still on screen, so nothing navigated away from the feed.
    await waitFor(() => expect(screen.getByTestId("case-card")).toBeInTheDocument());
    expect(screen.getByRole("link")).toHaveAttribute("href", "/cases/3");
  });

  it("says what the last activity was only where the feed sorts on it", () => {
    // The personal feed orders by activity, so it explains its own order. The
    // courtroom feed does not, and the line would be noise there.
    const { unmount } = draw({ showActivity: true });
    expect(screen.getByText(/פעילות אחרונה/)).toBeInTheDocument();

    unmount();
    draw({ showActivity: false });
    expect(screen.queryByText(/פעילות אחרונה/)).not.toBeInTheDocument();
  });

  it("marks a filing by one of the court's own personalities", () => {
    draw({
      case: testCase({
        author: { id: 9, name: "השופטת", avatar_url: null, is_bot: true },
      }),
    });

    expect(screen.getByTitle("חשבון בוט")).toBeInTheDocument();
  });
});
