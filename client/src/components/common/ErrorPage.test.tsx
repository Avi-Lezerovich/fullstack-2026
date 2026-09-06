import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorPage } from "./ErrorPage";

/**
 * The shared shell every refusal in the app is drawn with.
 *
 * Two things are worth pinning: that the caller's four pieces all reach the
 * page, and that the seal stays decorative. The seal repeats what the code and
 * the title already say, so announcing it would make a screen reader read the
 * same refusal three times.
 */

describe("ErrorPage", () => {
  it("shows the code, the title, the description and the action", () => {
    render(
      <ErrorPage
        code="404"
        title="התיק לא נמצא בארכיון"
        description="ייתכן שהכתובת הוקלדה בטעות."
        action={<button type="button">חזרה לאולם הראשי</button>}
      />,
    );

    expect(screen.getByTestId("error-page")).toHaveAttribute("data-code", "404");
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "התיק לא נמצא בארכיון" })).toBeInTheDocument();
    expect(screen.getByText("ייתכן שהכתובת הוקלדה בטעות.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "חזרה לאולם הראשי" })).toBeInTheDocument();
  });

  it("leaves the seal out of the accessibility tree", () => {
    const { container } = render(<ErrorPage code="500" title="התקלה נרשמה בפרוטוקול" />);

    const seal = container.querySelector("img");

    expect(seal).toHaveAttribute("alt", "");
    expect(seal).toHaveAttribute("aria-hidden");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders without a description or an action", () => {
    render(<ErrorPage code="403" title="הדלת הזו נעולה" />);

    expect(screen.getByTestId("error-page")).toHaveAttribute("data-code", "403");
  });
});
