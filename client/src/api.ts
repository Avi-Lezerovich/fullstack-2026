/**
 * Centralized API layer.
 * Every fetch in the app goes through here — components never call fetch directly.
 * All requests hit the real backend at /api (proxied to Flask in dev — see vite.config.ts).
 *
 * Auth is cookie-based (lecture 5 stateful sessions): the server sets an httpOnly
 * `session_id` cookie on login/signup. We send `credentials: "include"` on every
 * request so that cookie rides along; the token itself is invisible to JS.
 */
import type {
  AuthResponse,
  Post,
  User,
  UserListItem,
  UserProfileResponse,
} from "./types";

const BASE = "/api";

// ---------------------------------------------------------------- helpers

/** Wraps fetch with consistent error handling — throws the server's error message if !res.ok. */
const request = async <T>(url: string, init: RequestInit = {}): Promise<T> => {
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "include", // send/receive the session cookie
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    });
  } catch {
    throw new Error("שגיאת רשת. ודא שהשרת פעיל.");
  }

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    const msg =
      body && typeof body === "object" && "error" in body && typeof (body as { error: unknown }).error === "string"
        ? (body as { error: string }).error
        : `שגיאה ${res.status}`;
    throw new Error(msg);
  }

  return body as T;
};

// ----------------------------------------------------------------- auth

export const signup = (name: string, email: string, password: string): Promise<AuthResponse> =>
  request<AuthResponse>(`${BASE}/auth/signup`, {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });

export const login = (email: string, password: string): Promise<AuthResponse> =>
  request<AuthResponse>(`${BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

/** Destroy the server-side session (and cookie), then clear the local UI hint. */
export const logout = async (): Promise<void> => {
  try {
    await request(`${BASE}/auth/logout`, { method: "POST" });
  } finally {
    clearSession();
  }
};

// ----------------------------------------------------------------- posts

export const fetchPosts = (
  opts: { limit?: number; offset?: number; feed?: "global" | "following" } = {},
): Promise<Post[]> => {
  const sp = new URLSearchParams();
  if (typeof opts.limit === "number") sp.set("limit", String(opts.limit));
  if (typeof opts.offset === "number") sp.set("offset", String(opts.offset));
  if (opts.feed === "following") sp.set("feed", "following");
  return request<Post[]>(`${BASE}/posts?${sp.toString()}`);
};

export const createPost = (payload: {
  title: string;
  body: string;
  defendant: string;
  charges?: string[];
  image_url?: string | null;
}): Promise<Post> =>
  request<Post>(`${BASE}/posts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

// ----------------------------------------------------------------- users

export const fetchUsers = (opts: { search?: string; limit?: number; offset?: number } = {}): Promise<UserListItem[]> => {
  const sp = new URLSearchParams();
  if (opts.search) sp.set("search", opts.search);
  if (typeof opts.limit === "number") sp.set("limit", String(opts.limit));
  if (typeof opts.offset === "number") sp.set("offset", String(opts.offset));
  return request<UserListItem[]>(`${BASE}/users?${sp.toString()}`);
};

export const fetchUserProfile = (id: number): Promise<UserProfileResponse> =>
  request<UserProfileResponse>(`${BASE}/users/${id}`);

export const followUser = (id: number): Promise<{ is_following: boolean }> =>
  request<{ is_following: boolean }>(`${BASE}/users/${id}/follow`, { method: "POST" });

export const unfollowUser = (id: number): Promise<{ is_following: boolean }> =>
  request<{ is_following: boolean }>(`${BASE}/users/${id}/follow`, { method: "DELETE" });

/** Patch the logged-in user's editable profile fields. Returns the updated user. */
export const updateProfile = (payload: { bio?: string; avatar_url?: string }): Promise<AuthResponse> =>
  request<AuthResponse>(`${BASE}/users/me`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

/**
 * Upload an image (multipart). Bypasses the JSON `request` helper because the
 * browser must set its own multipart boundary on the Content-Type header.
 */
export const uploadImage = async (file: File): Promise<{ url: string }> => {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${BASE}/uploads`, { method: "POST", credentials: "include", body: form });
  } catch {
    throw new Error("שגיאת רשת. ודא שהשרת פעיל.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const msg =
      body && typeof body === "object" && "error" in body && typeof (body as { error: unknown }).error === "string"
        ? (body as { error: string }).error
        : `שגיאה ${res.status}`;
    throw new Error(msg);
  }
  return body as { url: string };
};

// ----------------------------------------------------------- session helpers
//
// The real auth lives in the httpOnly cookie (unreadable from JS). We still cache
// the public `user` object in localStorage as a UI hint — to greet the user and to
// gate routes without a round-trip. A stale hint just yields a 401 the UI handles.

export const getStoredUser = (): User | null => {
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
};

export const isLoggedIn = (): boolean => !!getStoredUser();

export const saveSession = (user: User): void => {
  localStorage.setItem("user", JSON.stringify(user));
  // Notify same-tab listeners (the native "storage" event only fires for OTHER tabs).
  window.dispatchEvent(new Event("auth-change"));
};

export const clearSession = (): void => {
  localStorage.removeItem("user");
  window.dispatchEvent(new Event("auth-change"));
};
