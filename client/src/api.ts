/**
 * The single place this application talks to the network.
 *
 * No component calls `fetch` directly. Everything goes through `request<T>`,
 * which means credentials handling, JSON parsing and error translation exist
 * once rather than in thirty components.
 *
 * Errors are thrown as `Error` carrying the server's own Hebrew `error` string,
 * so a caller's `catch` block already has something worth showing a user.
 */

import type {
  AuthResponse,
  Case,
  CaseListResponse,
  Comment,
  Conversation,
  CourtAgent,
  FlaggedItem,
  MeResponse,
  Message,
  ModerationAction,
  ModerationStatus,
  NewCaseInput,
  Notification,
  OkResponse,
  Report,
  PendingSummons,
  Summons,
  TrialView,
  UserListResponse,
  UserProfile,
  User,
  UserRef,
} from "./types";

const BASE = "/api";

/** An error that still knows the HTTP status and the server's error code. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      // Authentication is an httpOnly cookie; without this the browser will
      // not attach it and every request looks anonymous.
      credentials: "include",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });
  } catch {
    throw new ApiError("שגיאת רשת. ודא שהשרת פעיל ונסה שוב.", 0, "network");
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // 204s and empty error pages are both legitimate.
  }

  if (!response.ok) {
    const payload = (body ?? {}) as { error?: string; code?: string };
    throw new ApiError(
      payload.error || `שגיאה ${response.status}`,
      response.status,
      payload.code || "error",
    );
  }

  return body as T;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  ...(data === undefined ? {} : { body: JSON.stringify(data) }),
});

const query = (params: Record<string, string | number | boolean | undefined>): string => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

// --- auth -------------------------------------------------------------------

export const signup = (name: string, email: string, password: string) =>
  request<AuthResponse>("/auth/signup", json("POST", { name, email, password }));

export const login = (email: string, password: string) =>
  request<AuthResponse>("/auth/login", json("POST", { email, password }));

export const logout = () => request<OkResponse>("/auth/logout", json("POST"));

export const fetchMe = () => request<MeResponse>("/auth/me");

export const requestPasswordReset = (email: string) =>
  request<OkResponse>("/auth/password-reset/request", json("POST", { email }));

export const confirmPasswordReset = (token: string, password: string) =>
  request<OkResponse>("/auth/password-reset/confirm", json("POST", { token, password }));

// --- cases ------------------------------------------------------------------

export const fetchCases = (params: {
  limit?: number;
  offset?: number;
  author_id?: number;
  status?: string;
} = {}) => request<CaseListResponse>(`/cases${query(params)}`);

export const fetchCase = (caseId: number) =>
  request<{ case: Case }>(`/cases/${caseId}`).then((r) => r.case);

export const createCase = (input: NewCaseInput) =>
  request<{ case: Case }>("/cases", json("POST", input)).then((r) => r.case);

export const deleteCase = (caseId: number) =>
  request<OkResponse>(`/cases/${caseId}`, json("DELETE"));

// --- likes and comments -----------------------------------------------------

/** One endpoint for both directions: the server owns the current state. */
export const toggleLike = (caseId: number) =>
  request<{ liked: boolean; like_count: number }>(`/cases/${caseId}/like`, json("POST"));

export const fetchLikers = (caseId: number) =>
  request<{ users: UserRef[] }>(`/cases/${caseId}/likes`).then((r) => r.users);

export const fetchComments = (caseId: number) =>
  request<{ comments: Comment[] }>(`/cases/${caseId}/comments`).then((r) => r.comments);

export const createComment = (caseId: number, body: string, parentCommentId?: number | null) =>
  request<{ comment: Comment }>(
    `/cases/${caseId}/comments`,
    json("POST", { body, parent_comment_id: parentCommentId ?? null }),
  ).then((r) => r.comment);

// --- the trial --------------------------------------------------------------

export const fetchTrial = (caseId: number) => request<TrialView>(`/cases/${caseId}/trial`);

export const summonWitness = (caseId: number, witnessUserId: number) =>
  request<{ summons: Summons[] }>(
    `/cases/${caseId}/summons`,
    json("POST", { witness_user_id: witnessUserId }),
  ).then((r) => r.summons);

export const testify = (caseId: number, body: string) =>
  request<{ comment_id: number }>(`/cases/${caseId}/testify`, json("POST", { body }));

export const fetchMySummons = () =>
  request<{ summons: PendingSummons[] }>("/me/summons").then((r) => r.summons);

/** The court's permanent staff — the bots behind /about. */
export const fetchAgents = () =>
  request<{ agents: CourtAgent[] }>("/agents").then((r) => r.agents);

// --- people -----------------------------------------------------------------

export const fetchUsers = (params: {
  search?: string;
  limit?: number;
  offset?: number;
  include_bots?: boolean;
} = {}) =>
  request<UserListResponse>(
    `/users${query({ ...params, include_bots: params.include_bots === false ? 0 : undefined })}`,
  );

export const fetchUser = (userId: number) =>
  request<{ user: UserProfile }>(`/users/${userId}`).then((r) => r.user);

export const updateMyProfile = (patch: { name?: string; bio?: string; avatar_url?: string }) =>
  request<AuthResponse>("/users/me", json("PATCH", patch));

// --- direct messages --------------------------------------------------------

export const fetchConversations = () =>
  request<{ conversations: Conversation[]; unread_total: number }>("/conversations");

export const fetchThread = (conversationId: number) =>
  request<{ messages: Message[] }>(`/conversations/${conversationId}`).then((r) => r.messages);

/**
 * Which conversation, if any, you already have with this person.
 *
 * A GET: it creates nothing. `conversation_id` is null when you have never
 * spoken, and the row is written by the first message instead — so opening a
 * profile and walking away no longer leaves an empty thread behind.
 */
export const findConversationWith = (userId: number) =>
  request<{ conversation_id: number | null; recipient: UserRef }>(
    `/conversations/with/${userId}`,
  );

export const sendMessage = (recipientId: number, body: string) =>
  request<{ message_id: number; conversation_id: number }>(
    "/messages",
    json("POST", { recipient_id: recipientId, body }),
  );

// --- writing help -----------------------------------------------------------

export const draftLawsuit = (input: {
  defendant_text?: string;
  title?: string;
  charges?: string[];
  hint?: string;
}) => request<{ body: string; backend: string }>("/assist/draft-lawsuit", json("POST", input));

export const suggestComment = (caseId: number) =>
  request<{ body: string; backend: string }>("/assist/suggest-comment", json("POST", { case_id: caseId }));

/** The same suggestion, written in the voice of one of the court's own. */
export const suggestInCharacter = (agentUserId: number, hint: string) =>
  request<{ body: string; personality_name: string }>(
    "/assist/in-character",
    json("POST", { agent_user_id: agentUserId, hint }),
  );

// --- image uploads ----------------------------------------------------------

/**
 * Upload one image and get back the URL to reference it by.
 *
 * Deliberately does NOT go through `request<T>`: that helper sets
 * `Content-Type: application/json` on every call, and a multipart body must be
 * left alone so the browser can generate the boundary itself. Setting it by
 * hand is the classic way to make an upload fail with a parse error the
 * server cannot explain.
 */
export async function uploadImage(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${BASE}/uploads`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
  } catch {
    throw new ApiError("שגיאת רשת. ודא שהשרת פעיל ונסה שוב.", 0, "network");
  }

  if (!response.ok) {
    // A 413 comes from nginx or Werkzeug, not from our code, so it has no
    // Hebrew body to read - say the useful thing ourselves.
    if (response.status === 413) {
      throw new ApiError("הקובץ גדול מדי.", 413, "invalid");
    }
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      code?: string;
    };
    throw new ApiError(
      payload.error || `שגיאה ${response.status}`,
      response.status,
      payload.code || "error",
    );
  }

  const body = (await response.json()) as { url: string };
  return body.url;
}

// --- notifications ----------------------------------------------------------

/**
 * `since` is the polling fallback's request; without it, the newest first.
 * The SSE stream reads the same rows through the same cursor.
 */
export const fetchNotifications = (since?: number) =>
  request<{ notifications: Notification[]; unread_count: number; latest_id: number }>(
    `/notifications${query({ since })}`,
  );

export const markNotificationsRead = (ids?: number[]) =>
  request<{ marked: number; unread_count: number }>(
    "/notifications/read",
    json("POST", ids ? { ids } : {}),
  );

// --- moderation -------------------------------------------------------------

export const reportContent = (
  targetType: "case" | "comment",
  targetId: number,
  reason: string,
  details?: string,
) =>
  request<{ report_id: number; message: string }>(
    "/reports",
    json("POST", { target_type: targetType, target_id: targetId, reason, details }),
  );

export const fetchReportQueue = (status?: string) =>
  request<{ reports: Report[] }>(`/admin/queue${query({ status })}`).then((r) => r.reports);

export const fetchFlagged = () =>
  request<{ items: FlaggedItem[] }>("/admin/flagged").then((r) => r.items);

export const fetchModerationHistory = (targetType: string, targetId: number) =>
  request<{ history: ModerationAction[] }>(`/admin/history/${targetType}/${targetId}`).then(
    (r) => r.history,
  );

export const setContentStatus = (
  targetType: "case" | "comment",
  targetId: number,
  status: ModerationStatus,
  reason?: string,
) =>
  request<{ ok: true; status: string; changed: boolean }>(
    `/admin/content/${targetType}/${targetId}/status`,
    json("POST", { status, reason }),
  );

export const resolveReport = (reportId: number, decision: string, note?: string) =>
  request<OkResponse>(`/admin/reports/${reportId}/resolve`, json("POST", { decision, note }));

/** Suspended accounts. `GET /users` only ever returns active ones. */
export const fetchBannedUsers = () =>
  request<{ users: User[]; total: number }>("/admin/users/banned").then((r) => r.users);

export const banUser = (userId: number, reason?: string) =>
  request<{ ok: true; changed: boolean }>(`/admin/users/${userId}/ban`, json("POST", { reason }));

export const unbanUser = (userId: number) =>
  request<{ ok: true; changed: boolean }>(`/admin/users/${userId}/unban`, json("POST"));

// --- diagnostics ------------------------------------------------------------

export interface HealthResponse {
  status: string;
  database: string;
  phase_minutes: number;
  brain: string;
  worker: {
    tick_count: number;
    last_tick_at: string | null;
    seconds_since_tick: number | null;
    last_error: string | null;
  } | null;
}

export const fetchHealth = () => request<HealthResponse>("/health");
