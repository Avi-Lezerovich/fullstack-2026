/** Formatting helpers shared across the UI. */

/** Server timestamps are naive UTC ISO strings; the `Z` makes that explicit. */
export const parseServerDate = (value: string | null): Date | null => {
  if (!value) return null;
  const normalised = value.endsWith("Z") ? value : `${value}Z`;
  const date = new Date(normalised);
  return Number.isNaN(date.getTime()) ? null : date;
}

const rtf = new Intl.RelativeTimeFormat("he", { numeric: "auto" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60],
  ["month", 30 * 24 * 60 * 60],
  ["day", 24 * 60 * 60],
  ["hour", 60 * 60],
  ["minute", 60],
];

/** "לפני 5 דקות". */
export const relativeTime = (value: string | null): string => {
  const date = parseServerDate(value);
  if (!date) return "";

  const seconds = (date.getTime() - Date.now()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return "ממש עכשיו";
}

/** "בעוד 3 שעות" / "הסתיים" — used for the countdown to the next phase. */
export const timeUntil = (value: string | null): string => {
  const date = parseServerDate(value);
  if (!date) return "";
  return date.getTime() <= Date.now() ? "הסתיים" : relativeTime(value);
}

export const formatDate = (value: string | null): string => {
  const date = parseServerDate(value);
  return date
    ? date.toLocaleDateString("he-IL", { day: "numeric", month: "long", year: "numeric" })
    : "";
}

/** Initials for an avatar, tolerant of one-word names. */
export const initials = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return parts[0][0] + parts[1][0];
}
