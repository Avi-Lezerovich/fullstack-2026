/**
 * Shared validation helpers for the auth forms (login + signup).
 * Pure functions / constants — no React dependencies.
 */

/** RFC-5322-style email check, intentionally loose: rejects whitespace and missing `@`/`.`. */
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Minimum password length enforced by the signup form. Surfaces in error copy too. */
export const MIN_PASSWORD = 8;

/**
 * Hard signup rules: enforce a minimum length and a mix of letters and digits.
 * Returns a Hebrew error message, or null when the password is acceptable.
 */
export const validatePassword = (password: string): string | null => {
  if (password.length < MIN_PASSWORD) {
    return `הסיסמה חייבת להכיל לפחות ${MIN_PASSWORD} תווים`;
  }
  if (!/[A-Za-z]/.test(password)) {
    return "הסיסמה חייבת לכלול לפחות אות אחת";
  }
  if (!/\d/.test(password)) {
    return "הסיסמה חייבת לכלול לפחות ספרה אחת";
  }
  return null;
};

export type PasswordStrength = {
  /** 0–5, where 0 is empty and 5 is a long, mixed, symbol-bearing password. */
  score: number;
  /** Hebrew label for the meter ("" when empty). */
  label: string;
  /** MUI palette colour for the meter and label. */
  color: "error" | "warning" | "success";
};

/**
 * Live strength estimate for the signup meter (UX only — the hard gate is
 * validatePassword). Each satisfied criterion adds a point.
 */
export const passwordStrength = (password: string): PasswordStrength => {
  if (!password) return { score: 0, label: "", color: "error" };

  let score = 0;
  if (password.length >= MIN_PASSWORD) score++;
  if (password.length >= 12) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++; // mixed case
  if (/\d/.test(password)) score++; // a digit
  if (/[^A-Za-z0-9]/.test(password)) score++; // a symbol

  const levels: ReadonlyArray<Omit<PasswordStrength, "score">> = [
    { label: "חלשה מאוד", color: "error" },
    { label: "חלשה", color: "error" },
    { label: "בינונית", color: "warning" },
    { label: "טובה", color: "warning" },
    { label: "חזקה", color: "success" },
    { label: "חזקה מאוד", color: "success" },
  ];
  const { label, color } = levels[Math.min(score, levels.length - 1)];
  return { score, label, color };
};
