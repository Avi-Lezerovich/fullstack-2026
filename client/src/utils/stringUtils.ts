/**
 * Builds an avatar initial-string from a display name.
 * Splits on whitespace, takes the first letter of each part, caps at 2 chars.
 * Returns "" for empty input so callers can render an empty Avatar safely.
 * @param name - The display name to extract initials from.
 * @returns A 1-2 character string of initials, or empty string if input is empty.
 * @example
 * getInitials("John Doe") // "JD"
 * getInitials("אבי לזרוביץ") // "אל"
 */
export const getInitials = (name: string): string => {
  if (!name) return "";
  return name.split(/\s+/).map((p) => p[0]).filter(Boolean).slice(0, 2).join("");
};
