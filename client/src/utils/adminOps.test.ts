import { describe, expect, it } from "vitest";

import { hasBrainMismatch, isWorkerTicking, quotaSeverity } from "./adminOps";
import type { BrainStatus } from "../api";

/**
 * The three judgment calls behind the ops dashboard's System Health and AI
 * Usage tabs - pulled out of their components specifically so they can be
 * pinned here rather than through rendered markup, per this project's own
 * testing convention (see TESTING.md).
 */

const brain = (overrides: Partial<BrainStatus> = {}): BrainStatus => ({
  configured: "llm",
  last_backend: "llm",
  last_error: null,
  llm_calls: 0,
  llm_failures: 0,
  cache_reads: 0,
  cache_writes: 0,
  missing_capability: null,
  ...overrides,
});

describe("isWorkerTicking", () => {
  it("is ticking just under the threshold", () => {
    expect(isWorkerTicking(119)).toBe(true);
  });

  it("is stale at and past the threshold", () => {
    expect(isWorkerTicking(120)).toBe(false);
    expect(isWorkerTicking(500)).toBe(false);
  });

  it("treats a worker that has never ticked as stale, not as fresh", () => {
    expect(isWorkerTicking(null)).toBe(false);
  });
});

describe("hasBrainMismatch", () => {
  it("is not a mismatch when configured and last_backend agree", () => {
    expect(hasBrainMismatch(brain({ configured: "llm", last_backend: "llm" }))).toBe(false);
    expect(hasBrainMismatch(brain({ configured: "offline", last_backend: "offline" }))).toBe(
      false,
    );
  });

  it("is the exact failure the brain module's docstring warns about", () => {
    // configured says llm, but the last real call actually answered offline -
    // credentials look fine on paper while the backend is silently dead.
    expect(hasBrainMismatch(brain({ configured: "llm", last_backend: "offline" }))).toBe(true);
  });

  it("does not treat a fresh process that has made no call yet as a mismatch", () => {
    expect(hasBrainMismatch(brain({ configured: "llm", last_backend: "unknown" }))).toBe(false);
  });
});

describe("quotaSeverity", () => {
  it("reads as fine comfortably under the cap", () => {
    expect(quotaSeverity(5, 20)).toBe("ok");
  });

  it("turns into a warning once more than half is spent", () => {
    expect(quotaSeverity(12, 20)).toBe("warning");
  });

  it("turns urgent once the quota is nearly gone", () => {
    expect(quotaSeverity(19, 20)).toBe("error");
  });

  it("treats an unknown cap as fine rather than as an emergency", () => {
    // A cap of 0 means "allowance not published" - a paid account, or Bedrock
    // - and is the common case rather than the odd one. Reading it as an
    // error lit every uncapped credential red, which teaches a reader to
    // ignore the colour on the one tile where it means something.
    expect(quotaSeverity(0, 0)).toBe("ok");
    expect(quotaSeverity(5000, 0)).toBe("ok");
  });
});
