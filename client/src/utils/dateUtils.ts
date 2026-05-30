/**
 * Date formatting helpers used across the UI.
 * All output is in Hebrew (he-IL locale). Inputs are ISO 8601 strings from the API.
 */

/**
 * Relative time in Hebrew — "ממש עכשיו" / "לפני 5 דקות" / "אתמול" / falls back to a full date.
 * Used for "posted X ago" timestamps that should feel fresh.
 */
export const formatRelative = (iso: string): string => {
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const sec = Math.max(0, Math.floor(diffMs / 1000));
  if (sec < 60) return "ממש עכשיו";
  const min = Math.floor(sec / 60);
  if (min < 60) return min === 1 ? "לפני דקה" : `לפני ${min} דקות`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return hr === 1 ? "לפני שעה" : `לפני ${hr} שעות`;
  const day = Math.floor(hr / 24);
  if (day < 30) return day === 1 ? "אתמול" : `לפני ${day} ימים`;
  return d.toLocaleDateString("he-IL");
};

// Module-level formatter — instantiating Intl.DateTimeFormat is expensive,
// so we build it once and reuse it for every formatHebrewDate call.
const HEBREW_LONG_DATE = new Intl.DateTimeFormat("he-IL", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

/**
 * Long-form Hebrew date — e.g. "5 במאי 2026".
 * Used for non-relative timestamps like "joined on ..." on profile pages.
 */
export const formatHebrewDate = (iso: string): string =>
  HEBREW_LONG_DATE.format(new Date(iso));
