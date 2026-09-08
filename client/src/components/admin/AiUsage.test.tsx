import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AiUsage from "./AiUsage";
import * as api from "../../api";
import type { BrainUsageResponse } from "../../api";

/**
 * The tab exists to answer two questions an operator actually asks, and each
 * of them was previously unanswerable.
 *
 * "Which key ran out?" — a single provider-wide gauge could not say, because
 * quota belongs to a key and a model rather than to a vendor.
 *
 * "Why is nothing working?" — a backend where every call errors and one that
 * is merely near its cap produce the same climbing number, and the sentence
 * telling them apart sat unread in the database.
 */

vi.mock("../../api");

const usage = (over: Partial<BrainUsageResponse> = {}): BrainUsageResponse => ({
  today: [],
  week: [],
  credentials: [],
  by_credential: [],
  by_credential_week: [],
  failures: [],
  ...over,
});

const quota = (over = {}) => ({
  credential: "api1-gemini",
  provider: "gemini",
  model: "gemini-2.5-flash-lite",
  used: 10,
  cap: 1000,
  remaining: 990,
  exhausted: false,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
});

const load = (data: BrainUsageResponse) =>
  vi.mocked(api.fetchBrainUsage).mockResolvedValue(data);

describe("the failure panel", () => {
  it("shows the reason, so a wrong model id is readable rather than guessed at", async () => {
    load(
      usage({
        failures: [
          {
            provider: "gemini",
            reason: "GeminiHttpError: gemini HTTP 404: NOT_FOUND models/gemini-3.7-flash",
            calls: 57,
            last_seen: "2026-09-08T10:00:00",
          },
        ],
      }),
    );

    render(<AiUsage />);

    const panel = await screen.findByTestId("brain-failures");
    expect(within(panel).getByText(/models\/gemini-3\.7-flash/)).toBeInTheDocument();
    expect(within(panel).getByText("57×")).toBeInTheDocument();
  });

  it("renders the reason left-to-right inside the RTL page", async () => {
    // Not styling. In the surrounding direction the browser reorders the
    // English text, and a reader ends up debugging a model name that is not
    // the one that failed.
    load(
      usage({
        failures: [
          { provider: "gemini", reason: "HTTP 404 models/x", calls: 1, last_seen: "2026-09-08T10:00:00" },
        ],
      }),
    );

    render(<AiUsage />);

    const panel = await screen.findByTestId("brain-failures");
    expect(within(panel).getByText(/models\/x/).closest("[dir]")).toHaveAttribute("dir", "ltr");
  });

  it("stays out of the way when nothing is failing", async () => {
    load(usage({ credentials: [quota()] }));

    render(<AiUsage />);

    await screen.findByTestId("credential-quota");
    expect(screen.queryByTestId("brain-failures")).not.toBeInTheDocument();
  });
});

describe("the per-credential quota tiles", () => {
  it("names the key and the model the allowance belongs to", async () => {
    load(usage({ credentials: [quota()] }));

    render(<AiUsage />);

    const tile = await screen.findByTestId("credential-quota");
    expect(within(tile).getByText("api1-gemini")).toBeInTheDocument();
    expect(within(tile).getByText("gemini-2.5-flash-lite")).toBeInTheDocument();
    expect(within(tile).getByText("10/1,000")).toBeInTheDocument();
  });

  it("gives every configured key its own tile", async () => {
    load(
      usage({
        credentials: [
          quota(),
          quota({ credential: "api2-gemini", used: 0, remaining: 1000 }),
          quota({ credential: "api3-bedrock", provider: "bedrock", model: "anthropic.claude-opus-5", cap: 100, used: 4, remaining: 96 }),
        ],
      }),
    );

    render(<AiUsage />);

    await waitFor(() => expect(screen.getAllByTestId("credential-quota")).toHaveLength(3));
    expect(screen.getByText("api3-bedrock")).toBeInTheDocument();
  });

  it("says an exhausted key has handed over rather than showing a full bar", async () => {
    load(usage({ credentials: [quota({ used: 1000, remaining: 0, exhausted: true })] }));

    render(<AiUsage />);

    const tile = await screen.findByTestId("credential-quota");
    expect(within(tile).getByText(/עוברות למפתח הבא/)).toBeInTheDocument();
  });

  it("states an unknown cap instead of drawing a meaningless bar", async () => {
    // `cap: 0` is honest for a paid account. A progress bar with no
    // denominator is either always empty or always full and means neither.
    load(usage({ credentials: [quota({ cap: 0, used: 42, remaining: 0 })] }));

    render(<AiUsage />);

    const tile = await screen.findByTestId("credential-quota");
    expect(within(tile).getByText(/לא הוגדרה מכסה/)).toBeInTheDocument();
    expect(within(tile).getByText("42 קריאות")).toBeInTheDocument();
  });
});

describe("grouping", () => {
  it("switches the rows from provider to key", async () => {
    load(
      usage({
        today: [
          {
            provider: "gemini",
            calls: 3,
            successes: 3,
            failures: 0,
            fallback_to_offline: 0,
            input_tokens: 0,
            output_tokens: 0,
            cache_read: 0,
            cache_write: 0,
          },
        ],
        by_credential: [
          {
            credential: "api2-gemini",
            model: "gemini-2.5-flash-lite",
            provider: "gemini",
            calls: 3,
            successes: 3,
            failures: 0,
            fallback_to_offline: 0,
            input_tokens: 0,
            output_tokens: 0,
            cache_read: 0,
            cache_write: 0,
            avg_latency_ms: 210,
          },
        ],
      }),
    );

    render(<AiUsage />);

    await screen.findByText("Gemini");
    expect(screen.queryByText("api2-gemini")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "לפי מפתח" }));

    expect(await screen.findByText("api2-gemini")).toBeInTheDocument();
    expect(screen.getByText(/210 מ״ש בממוצע/)).toBeInTheDocument();
  });
});
