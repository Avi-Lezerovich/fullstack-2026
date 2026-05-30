/**
 * Shared TypeScript types — the API contract.
 * Mirrors the JSON shapes returned by the (mock) backend.
 */

export interface User {
  id: number;
  name: string;
  email: string;
  /** Short self-description (nullable). */
  bio?: string | null;
  /** URL/path to the profile picture (nullable). */
  avatar_url?: string | null;
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
  /** Sanitized rich-text HTML. */
  body: string;
  defendant: string;
  location?: string | null;
  /** URL/path to an attached image (nullable). */
  image_url?: string | null;
  charges?: string[];
  author_id: number;
  author_name: string;
  /** ISO 8601 datetime. */
  created_at: string;
}

export interface UserProfileResponse {
  user: User;
  posts: Post[];
  followers_count: number;
  following_count: number;
  /** Whether the current viewer follows this profile. */
  is_following: boolean;
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
