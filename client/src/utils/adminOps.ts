/** The judgment calls behind the ops dashboard's System Health and AI Usage
 * tabs, pulled out of the components so they can be asserted on directly
 * rather than through rendered markup. */

import type { BrainStatus } from "../api";

/** Matches CourtStatus's own threshold, so the badge there and the System
 * Health tab never disagree about what "stale" means for the same tick. */
export const STALE_AFTER_SECONDS = 120;

export const isWorkerTicking = (secondsSinceTick: number | null): boolean =>
  secondsSinceTick !== null && secondsSinceTick < STALE_AFTER_SECONDS;

/**
 * The exact failure mode brain/__init__.py's docstring warns about: intent
 * and outcome disagreeing. `last_backend` is "unknown" until this process has
 * made a single call, which is a startup transient rather than a broken
 * backend, so it is never reported as a mismatch.
 */
export const hasBrainMismatch = (brain: BrainStatus): boolean =>
  brain.last_backend !== "unknown" && brain.configured !== brain.last_backend;

export type QuotaSeverity = "ok" | "warning" | "error";

/**
 * <60% used reads as fine, <90% as worth watching, the rest as urgent.
 *
 * A cap of 0 means the allowance is not known - a paid account, or a provider
 * that publishes no number - and reads as "ok" rather than "error". Treating
 * an unknown cap as an emergency lit every uncapped credential red, which
 * trains a reader to ignore the colour on the one tile where it means
 * something.
 */
export const quotaSeverity = (used: number, cap: number): QuotaSeverity => {
  if (cap <= 0) return "ok";
  const ratio = used / cap;
  if (ratio >= 0.9) return "error";
  if (ratio >= 0.6) return "warning";
  return "ok";
};
