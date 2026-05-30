import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

describe("test infrastructure", () => {
  it("renders a basic component", () => {
    render(<h1>LolSuit</h1>);
    expect(screen.getByRole("heading", { name: "LolSuit" })).toBeInTheDocument();
  });
});
