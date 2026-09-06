import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatDate, initials, isPast, parseServerDate, relativeTime, timeUntil } from "./format";

/**
 * The formatting helpers, and the one bug they exist to prevent.
 *
 * Every timestamp this API returns is a NAIVE UTC ISO string - the schema
 * stores naive UTC everywhere and `isoformat()` writes no offset. A browser
 * handed "2026-09-06T10:00:00" parses it as LOCAL time, so in Israel every
 * timestamp in the application would read three hours early, and "לפני 3
 * שעות" would appear next to something posted seconds ago.
 *
 * `parseServerDate` appending the `Z` is the whole fix, and it is the reason
 * every other function here goes through it rather than calling `new Date`.
 *
 * The clock is frozen so "an hour ago" means an hour ago rather than an hour
 * ago from whenever the suite happened to run.
 */

const NOW = new Date("2026-09-06T12:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("parseServerDate", () => {
  it("reads a naive server timestamp as UTC rather than as local time", () => {
    // Without the appended Z this is off by the viewer's own offset, which is
    // silent, plausible, and wrong for everyone outside UTC.
    const parsed = parseServerDate("2026-09-06T10:00:00");

    expect(parsed?.toISOString()).toBe("2026-09-06T10:00:00.000Z");
  });

  it("leaves a timestamp that already declares UTC alone", () => {
    expect(parseServerDate("2026-09-06T10:00:00Z")?.toISOString()).toBe(
      "2026-09-06T10:00:00.000Z",
    );
  });

  it("answers null for nothing and for nonsense", () => {
    // Half the timestamps in the API are legitimately null - a case that has
    // not closed, a comment with no verdict - so this is the common path.
    expect(parseServerDate(null)).toBeNull();
    expect(parseServerDate("")).toBeNull();
    expect(parseServerDate("not a date")).toBeNull();
  });
});

describe("relativeTime", () => {
  it("counts back in the largest unit that fits", () => {
    expect(relativeTime("2026-09-06T09:00:00")).toBe(relativeTime("2026-09-06T09:00:00"));
    expect(relativeTime("2026-09-06T09:00:00")).toContain("3");
    expect(relativeTime("2026-08-06T12:00:00")).not.toBe("");
  });

  it("calls anything under a minute just now", () => {
    expect(relativeTime("2026-09-06T11:59:31")).toBe("ממש עכשיו");
  });

  it("reads forwards as well as backwards", () => {
    // Phase deadlines are in the future, and the same helper renders them.
    const future = relativeTime("2026-09-06T15:00:00");

    expect(future).not.toBe("");
    expect(future).not.toBe(relativeTime("2026-09-06T09:00:00"));
  });

  it("is empty rather than broken for a missing timestamp", () => {
    expect(relativeTime(null)).toBe("");
    expect(relativeTime("nonsense")).toBe("");
  });
});

describe("isPast", () => {
  it("is true once the moment has gone", () => {
    expect(isPast("2026-09-06T11:59:59")).toBe(true);
    expect(isPast("2026-09-06T12:00:01")).toBe(false);
  });

  it("treats a missing deadline as past", () => {
    // `phase_deadline_at` is NULL on a closed case, and a closed case is
    // certainly not still waiting - so null has to read as "done", not as
    // "forever".
    expect(isPast(null)).toBe(true);
  });
});

describe("timeUntil", () => {
  it("describes a future moment", () => {
    expect(timeUntil("2026-09-06T15:00:00")).not.toBe("");
  });

  it("is empty for anything that has already happened", () => {
    // Documented as "call only when the date is known to be in the future",
    // so the guard is what keeps a stale deadline from rendering as a
    // countdown that has run backwards.
    expect(timeUntil("2026-09-06T09:00:00")).toBe("");
    expect(timeUntil(NOW.toISOString())).toBe("");
    expect(timeUntil(null)).toBe("");
  });
});

describe("formatDate", () => {
  it("writes a Hebrew long date", () => {
    const written = formatDate("2026-09-06T10:00:00");

    expect(written).toContain("2026");
    expect(written).not.toBe("");
  });

  it("is empty for a missing date", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate("nonsense")).toBe("");
  });
});

describe("initials", () => {
  it("takes the first letter of the first two words", () => {
    expect(initials("דנה כהן")).toBe("דכ");
  });

  it("tolerates a one-word name by taking two letters from it", () => {
    // Bots have single-word personality names, so this is not an edge case.
    expect(initials("שופטת")).toBe("שו");
  });

  it("ignores the extra whitespace a pasted name arrives with", () => {
    expect(initials("  דנה   כהן  ")).toBe("דכ");
  });

  it("falls back to a question mark rather than crashing on an empty name", () => {
    expect(initials("")).toBe("?");
    expect(initials("   ")).toBe("?");
  });
});
