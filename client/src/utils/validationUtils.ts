/**
 * Shared validation helpers for the auth forms (login + signup).
 * Pure functions / constants — no React dependencies.
 */

/** RFC-5322-style email check, intentionally loose: rejects whitespace and missing `@`/`.`. */
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Minimum password length enforced by the signup form. Surfaces in error copy too. */
export const MIN_PASSWORD = 6;
