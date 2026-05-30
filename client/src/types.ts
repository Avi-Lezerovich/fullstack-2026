/**
 * Shared TypeScript types — the API contract.
 * Mirrors the JSON shapes returned by the (mock) backend.
 */

export interface User {
  id: number;
  name: string;
  email: string;
  /** ISO 8601 datetime. */
  created_at: string;
}

/** A user as returned by GET /api/users (with a computed post count). */
export interface UserListItem extends User {
  post_count: number;
}

export interface Post {
  id: number;
  title: string;
  body: string;
  defendant: string;
  location?: string | null;
  charges?: string[];
  author_id: number;
  author_name: string;
  /** ISO 8601 datetime. */
  created_at: string;
}

export interface UserProfileResponse {
  user: User;
  posts: Post[];
}

export interface AuthResponse {
  user: User;
}

/** Fixed list of charges available when filing a new lawsuit. */
export const CHARGES_OPTIONS = [
  "רשלנות פלילית",
  "הפרת שלוות נפש",
  "בגידה חברתית",
  "מניפולציה רגשית",
  "עיכוב כרוני",
  "ייאוש מכוון",
] as const;

export type ChargeOption = (typeof CHARGES_OPTIONS)[number];
