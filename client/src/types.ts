/**
 * Shared TypeScript types — the API contract.
 * Mirrors the JSON shapes returned by the Flask backend.
 */

export interface User {
  id: number;
  name: string;
  email: string;
  /** ISO 8601 datetime. */
  created_at: string;
}

/** A user as returned by GET /api/users (with computed stats). */
export interface UserListItem extends User {
  post_count: number;
  guilty_count: number;
  guilty_percent: number;
}

export interface Post {
  id: number;
  title: string;
  body: string;
  defendant: string;
  location?: string | null;
  charges?: string[];
  damages?: string | null;
  author_id: number;
  author_name: string;
  guilty_votes: number;
  innocent_votes: number;
  /** ISO 8601 datetime. */
  created_at: string;
}

export interface UserStats {
  total: number;
  guilty: number;
  innocent: number;
  success_percent: number;
}

export interface UserProfileResponse {
  user: User;
  stats: UserStats;
  posts: Post[];
}

export interface AuthResponse {
  token: string;
  user: User;
}

export type Sort = "new" | "hot" | "closed";

export type VoteSide = "guilty" | "innocent";

export interface VoteResponse {
  post_id: number;
  side: VoteSide;
  guilty_votes: number;
  innocent_votes: number;
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
