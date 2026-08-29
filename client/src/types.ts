/**
 * The shared contract with the backend.
 *
 * Every type here mirrors, field for field, what a service function in
 * `server/app/services/` returns — in particular `cases_service.shape_case`
 * and `users_service.public_user`. There is no code generation: the pairing is
 * kept by hand and by the integration tests, which assert on the same keys.
 */

// --- people -----------------------------------------------------------------

/** The compact form embedded inside a case or a comment. */
export interface UserRef {
  id: number;
  name: string;
  avatar_url: string | null;
  is_bot: boolean;
}

export interface User extends UserRef {
  bio: string | null;
  is_admin: boolean;
  status: "active" | "banned";
  created_at: string | null;
}

/** Only ever returned for the signed-in user themselves. */
export interface CurrentUser extends User {
  email: string;
}

export interface UserProfile extends User {
  case_count: number;
}

// --- the trial --------------------------------------------------------------

/**
 * The case lifecycle.
 *
 * `filed` is never observed in normal operation - `create_case` writes
 * `witness_phase` directly. It is kept deliberately, not left behind: it is
 * the state a row inserted by hand (a fixture, a restored dump, a migration)
 * would land in, and `trial_service.open_filed_cases` exists to sweep exactly
 * those onto the trial calendar. Without the status there is no name for that
 * case, and without the sweep such a row would sit forever with no deadline
 * and nothing to move it.
 */
export type CaseStatus =
  | "filed"
  | "witness_phase"
  | "jury_deliberation"
  | "verdict_reached"
  | "closed";

export type Verdict = "guilty" | "not_guilty";

/**
 * `flagged` is deliberately still public — borderline content stays up with a
 * marker. `hidden` and `rejected` are only ever seen by the author and admins.
 */
export type ModerationStatus = "published" | "flagged" | "hidden" | "rejected";

export interface Case {
  id: number;
  title: string;
  body: string;
  image_url: string | null;
  author: UserRef;
  /** Always present. Free text even when a registered defendant is named. */
  defendant_text: string;
  /** Non-null only when the defendant is a registered user. */
  defendant: UserRef | null;
  charges: string[];
  status: CaseStatus;
  /** When the current phase ends. Null once the case is closed. */
  phase_deadline_at: string | null;
  filed_at: string | null;
  verdict: Verdict | null;
  sentence_text: string | null;
  verdict_at: string | null;
  closed_at: string | null;
  moderation_status: ModerationStatus;
  created_at: string | null;
  like_count: number;
  comment_count: number;
  viewer_has_liked: boolean;
}


// --- comments ---------------------------------------------------------------

/**
 * Everything anybody says on a case lives in one table, distinguished by role.
 * `user` is a human comment; the other three are produced by the trial itself.
 */
export type CommentRole = "user" | "witness_testimony" | "jury_deliberation" | "verdict";

/** A comment's author, plus the court persona if the author is a bot. */
export interface CommentAuthor extends UserRef {
  personality_name: string | null;
}

export interface Comment {
  id: number;
  case_id: number;
  author: CommentAuthor;
  parent_comment_id: number | null;
  /** The top-level ancestor. A root comment is its own root. */
  root_comment_id: number | null;
  depth: number;
  /** Null when hidden and the viewer is not the author or an admin. */
  body: string | null;
  role: CommentRole;
  moderation_status: ModerationStatus;
  is_hidden: boolean;
  created_at: string | null;
}

export const COMMENT_ROLE_LABELS: Record<CommentRole, string> = {
  user: "תגובה",
  witness_testimony: "עדות",
  jury_deliberation: "דיון מושבעים",
  verdict: "פסק דין",
};

// --- the jury and the witnesses ---------------------------------------------

/** A bot's public face carries the court persona it plays. */
export interface CourtBot extends UserRef {
  personality_name: string | null;
}

export interface JuryMember {
  /** 0–6. Seat order is speaking order. */
  seat: number;
  juror: CourtBot;
  /** The moment this juror is scheduled to speak, fixed when the panel was drawn. */
  speaks_at: string | null;
  /** Null until they have spoken. */
  spoke_at: string | null;
  /** Null until they have spoken — the panel shows who is still to be heard. */
  vote: Verdict | null;
  comment_id: number | null;
}

export interface JuryPanel {
  judge: CourtBot;
  tally_guilty: number | null;
  tally_not_guilty: number | null;
  /** True only if a juror was missing a vote — seven jurors cannot tie. */
  tiebreak_used: boolean;
  members: JuryMember[];
}

/** One of the permanent court personalities, as /about shows them. */
export interface CourtAgent {
  id: number;
  name: string;
  bio: string | null;
  avatar_url: string | null;
  role: "juror" | "judge" | "moderator";
  /** Only ever set for moderators; the three of them are fixed, never drawn. */
  moderator_kind: "sweeper" | "clerk" | "arbiter" | null;
  personality_name: string;
  tone_tag: string;
}

export const AGENT_ROLE_LABELS: Record<CourtAgent["role"], string> = {
  judge: "הרכב השופטים",
  juror: "מאגר המושבעים",
  moderator: "צוות הפיקוח",
};

export const MODERATOR_KIND_LABELS: Record<string, string> = {
  clerk: "פקיד התורנות",
  arbiter: "הבורר",
  sweeper: "הסורק",
};

/** The twelve voices the offline generator can write in (server/app/seed_data.py). */
export const TONE_LABELS: Record<string, string> = {
  pedantic: "דקדקן",
  sentimental: "רגשן",
  deadpan: "יבש",
  pompous: "רברבן",
  chaotic: "כאוטי",
  bureaucratic: "בירוקרטי",
  folksy: "עממי",
  theatrical: "תיאטרלי",
  streetwise: "רחוב",
  mystic: "קוסמי",
  corporate: "תאגידי",
  conspiracy: "חשדן",
};

export type SummonsStatus = "pending" | "testified" | "no_show";

export interface Summons {
  id: number;
  case_id: number;
  witness: UserRef;
  summoned_by_user_id: number;
  side: "plaintiff" | "defense";
  status: SummonsStatus;
  deadline_at: string | null;
  responded_at: string | null;
  testimony_comment_id: number | null;
}

export interface PendingSummons extends Summons {
  case_title: string;
}

/**
 * What the viewer is allowed to do right now. Computed server-side so the
 * client never reimplements the phase and party rules.
 */
export interface TrialViewer {
  side: "plaintiff" | "defense" | null;
  can_summon: boolean;
  summons_remaining: number;
  can_testify: boolean;
}

export interface TrialView {
  panel: JuryPanel | null;
  summons: Summons[];
  viewer: TrialViewer;
}

export const SUMMONS_STATUS_LABELS: Record<SummonsStatus, string> = {
  pending: "ממתין לעדות",
  testified: "מסר עדות",
  no_show: "לא התייצב",
};

// --- direct messages --------------------------------------------------------

export interface Message {
  id: number;
  conversation_id: number;
  sender: { id: number; name: string };
  body: string;
  read_at: string | null;
  created_at: string;
  is_mine: boolean;
}

export interface Conversation {
  id: number;
  other: UserRef | null;
  last_message: { body: string; sender_id: number; created_at: string } | null;
  unread_count: number;
}

// --- moderation -------------------------------------------------------------

export type ReportStatus =
  | "open"
  | "claimed"
  | "resolved_hidden"
  | "resolved_dismissed"
  | "resolved_banned";

export interface Report {
  id: number;
  target_type: "case" | "comment";
  target_id: number;
  reason: string;
  details: string | null;
  status: ReportStatus;
  reporter: { id: number; name: string };
  resolver: { id: number; name: string } | null;
  resolution_note: string | null;
  created_at: string;
  excerpt: string;
  /** The case the reported item lives on. Null only if it has been deleted. */
  case_id: number | null;
}

export interface FlaggedItem {
  target_type: "case" | "comment";
  target_id: number;
  heading: string | null;
  excerpt: string;
  moderation_status: ModerationStatus;
  author: { id: number; name: string };
  created_at: string;
}

/** One line of the audit trail. `actor_is_bot` is what makes an override legible. */
export interface ModerationAction {
  id: number;
  actor: { id: number; name: string };
  actor_is_bot: boolean;
  action: string;
  previous_status: string | null;
  new_status: string | null;
  reason: string | null;
  created_at: string;
}

export const REPORT_REASONS = [
  { value: "abuse", label: "תוכן פוגעני" },
  { value: "harassment", label: "הטרדה" },
  { value: "spam", label: "ספאם" },
  { value: "off_topic", label: "לא רלוונטי" },
  { value: "other", label: "אחר" },
] as const;

export const REPORT_STATUS_LABELS: Record<ReportStatus, string> = {
  open: "ממתין",
  claimed: "בבדיקה",
  resolved_hidden: "הוסתר",
  resolved_dismissed: "נדחה",
  resolved_banned: "המשתמש הושעה",
};

export const MODERATION_STATUS_LABELS: Record<ModerationStatus, string> = {
  published: "מפורסם",
  flagged: "סומן לבדיקה",
  hidden: "מוסתר",
  rejected: "נחסם",
};

// --- notifications ----------------------------------------------------------

export type NotificationType =
  | "summons"
  | "verdict"
  | "like"
  | "comment"
  | "message"
  | "moderation"
  | "testimony";

export interface Notification {
  id: number;
  type: NotificationType;
  case_id: number | null;
  actor: { id: number; name: string } | null;
  payload: Record<string, unknown>;
  is_read: boolean;
  created_at: string | null;
}

// --- API envelopes ----------------------------------------------------------

export interface CaseListResponse {
  cases: Case[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserListResponse {
  users: User[];
  /** Matches the same filters as `users`, so it is safe to page against. */
  total: number;
  limit: number;
  offset: number;
}

export interface AuthResponse {
  user: CurrentUser;
}

export interface MeResponse {
  user: CurrentUser | null;
}

export interface OkResponse {
  ok: true;
  message?: string;
}

export interface NewCaseInput {
  title: string;
  body: string;
  defendant_text: string;
  defendant_user_id?: number | null;
  charges?: string[];
  image_url?: string | null;
}

// --- presentation helpers ---------------------------------------------------

/** Suggestions offered in the filing form; the server accepts free text too. */
export const CHARGE_SUGGESTIONS = [
  "גרימת עייפות",
  "הפרת שלווה",
  "הטרדה רגשית",
  "בזבוז זמן יקר",
  "רשלנות חמורה",
  "הפרת אמון",
  "גניבת דעת",
  "עוגמת נפש",
] as const;

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  filed: "הוגשה",
  witness_phase: "איסוף עדויות",
  jury_deliberation: "דיוני מושבעים",
  verdict_reached: "ניתן פסק דין",
  closed: "התיק נסגר",
};

export const VERDICT_LABELS: Record<Verdict, string> = {
  guilty: "חייב",
  not_guilty: "זכאי",
};
