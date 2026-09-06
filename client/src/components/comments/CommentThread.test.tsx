import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import CommentThread from "./CommentThread";
import type { Comment } from "../../types";

/**
 * The thread, which does no recursion at all.
 *
 * The server sends a flat array, already ordered so replies follow their root
 * and already carrying a `depth` — so what this component decides is narrower
 * than it looks, and that narrowness is the thing worth pinning:
 *
 *   - indentation is `depth * INDENT_PX` on `marginInlineStart`, a logical
 *     property, because the whole UI is RTL and `marginLeft` would indent the
 *     wrong way;
 *   - a hidden comment renders a placeholder rather than being omitted, so the
 *     conversation keeps its shape;
 *   - the composer closes only after `onReply` resolves;
 *   - court speech is not reportable, because the bots are the venue.
 *
 * A router is needed because each avatar links to its author's profile.
 */

const comment = (over: Partial<Comment> = {}): Comment => ({
  id: 1,
  case_id: 10,
  author: { id: 2, name: "דנה כהן", avatar_url: null, is_bot: false, personality_name: null },
  parent_comment_id: null,
  root_comment_id: null,
  depth: 0,
  body: "גם לי זה קרה.",
  role: "user",
  moderation_status: "published",
  is_hidden: false,
  created_at: "2026-09-06T10:00:00",
  ...over,
});

const draw = (comments: Comment[], props: Partial<React.ComponentProps<typeof CommentThread>> = {}) =>
  render(
    <MemoryRouter>
      <CommentThread
        comments={comments}
        canReply={props.canReply ?? true}
        onReply={props.onReply ?? vi.fn().mockResolvedValue(undefined)}
      />
    </MemoryRouter>,
  );

describe("CommentThread", () => {
  it("says so when nothing has been said yet", () => {
    draw([]);

    expect(screen.getByTestId("comments-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("comment-thread")).not.toBeInTheDocument();
  });

  it("renders the server's order without rearranging it", () => {
    // The ordering is `COALESCE(root_comment_id, id), created_at, id` — done
    // in SQL precisely so the client does not have to build a tree.
    draw([
      comment({ id: 1, body: "ראשונה" }),
      comment({ id: 2, body: "תשובה לראשונה", parent_comment_id: 1, root_comment_id: 1, depth: 1 }),
      comment({ id: 3, body: "שנייה" }),
    ]);

    const bodies = screen.getAllByTestId("comment-item").map((node) => node.textContent);
    expect(bodies[0]).toContain("ראשונה");
    expect(bodies[1]).toContain("תשובה לראשונה");
    expect(bodies[2]).toContain("שנייה");
  });

  it("indents each level with a logical property, not a left margin", () => {
    // `marginInlineStart` is what makes this indent from the right under RTL.
    draw([
      comment({ id: 1, depth: 0 }),
      comment({ id: 2, depth: 1, parent_comment_id: 1 }),
      comment({ id: 3, depth: 3, parent_comment_id: 2 }),
    ]);

    const items = screen.getAllByTestId("comment-item");

    expect(items.map((node) => node.getAttribute("data-depth"))).toEqual(["0", "1", "3"]);
    expect(items[0]).toHaveStyle({ marginInlineStart: "0px" });
    expect(items[1]).toHaveStyle({ marginInlineStart: "28px" });
    expect(items[2]).toHaveStyle({ marginInlineStart: "84px" });
  });

  it("shows a placeholder where removed content was, rather than closing the gap", async () => {
    // Omitting it would renumber the conversation: replies would appear to
    // answer whatever came before the gap.
    draw([
      comment({ id: 1, body: "ראשונה" }),
      comment({ id: 2, body: null, is_hidden: true, moderation_status: "hidden" }),
      comment({ id: 3, body: "שלישית" }),
    ]);

    expect(screen.getAllByTestId("comment-item")).toHaveLength(3);
    expect(screen.getByText("התוכן הוסר על ידי הפיקוח.")).toBeInTheDocument();
  });

  it("shows the body to a viewer who is allowed it even when it is hidden", () => {
    // The author and an admin get `body` back from the server, and the
    // component branches on `body === null` rather than on `is_hidden` alone —
    // so being told it was removed does not mean being shown nothing.
    draw([comment({ id: 1, body: "מה שנכתב", is_hidden: true, moderation_status: "hidden" })]);

    expect(screen.getByText("מה שנכתב")).toBeInTheDocument();
    expect(screen.queryByText("התוכן הוסר על ידי הפיקוח.")).not.toBeInTheDocument();
  });

  it("marks a bot so the reader knows who is speaking", () => {
    draw([
      comment({
        id: 1,
        role: "jury_deliberation",
        author: {
          id: 5,
          name: "השופטת",
          avatar_url: null,
          is_bot: true,
          personality_name: "השופטת הקפדנית",
        },
      }),
    ]);

    expect(screen.getByTitle("בוט")).toBeInTheDocument();
    expect(screen.getByTestId("comment-item")).toHaveAttribute("data-role", "jury_deliberation");
  });

  it("offers a reply on a comment and closes the composer once it lands", async () => {
    // Closing only after the promise resolves is what stops a failed reply
    // silently vanishing along with the text the user typed.
    const onReply = vi.fn().mockResolvedValue(undefined);
    draw([comment({ id: 8 })], { onReply });

    await userEvent.click(screen.getByRole("button", { name: "השב" }));
    const box = screen.getByPlaceholderText("תשובה…");
    await userEvent.type(box, "אני מסכים");
    await userEvent.click(screen.getByRole("button", { name: "שלח תשובה" }));

    await waitFor(() => expect(onReply).toHaveBeenCalledWith("אני מסכים", 8));
    await waitFor(() => expect(screen.queryByPlaceholderText("תשובה…")).not.toBeInTheDocument());
  });

  it("the reply box can be opened and dismissed again", async () => {
    draw([comment({ id: 8 })]);

    await userEvent.click(screen.getByRole("button", { name: "השב" }));
    expect(screen.getByPlaceholderText("תשובה…")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "ביטול" }));
    expect(screen.queryByPlaceholderText("תשובה…")).not.toBeInTheDocument();
  });

  it("offers no reply at all to a signed-out reader", () => {
    draw([comment({ id: 8 })], { canReply: false });

    expect(screen.queryByRole("button", { name: "השב" })).not.toBeInTheDocument();
  });

  it("offers no reply on removed content", () => {
    // There is nothing to answer, and a thread of replies to a placeholder is
    // a conversation about something nobody can read.
    draw([comment({ id: 8, body: null, is_hidden: true })]);

    expect(screen.queryByRole("button", { name: "השב" })).not.toBeInTheDocument();
  });

  it("court speech is not reportable", () => {
    // The bots are the venue, not participants in it — reporting a verdict
    // would put the court in its own queue.
    draw([
      comment({ id: 1, role: "user" }),
      comment({ id: 2, role: "verdict" }),
      comment({ id: 3, role: "witness_testimony" }),
      comment({ id: 4, role: "jury_deliberation" }),
    ]);

    // One report control, on the one ordinary comment.
    expect(screen.getAllByTestId("report-button")).toHaveLength(1);
  });
});
