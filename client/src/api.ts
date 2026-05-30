/**
 * Centralized API layer.
 * Every fetch in the app goes through here — components never call fetch directly.
 * When USE_MOCK_DATA is on (dev), calls are served by the in-memory mock backend.
 */
import type {
  AuthResponse,
  Post,
  User,
  UserListItem,
  UserProfileResponse,
} from "./types";
import {
  mockCreatePost,
  mockFetchPosts,
  mockFetchUserProfile,
  mockFetchUsers,
  mockLogin,
  mockSignup,
} from "./mockApi";

const BASE = "/api";
const USE_MOCK_DATA = import.meta.env.DEV || import.meta.env.VITE_USE_MOCK_DATA === "true";

// ---------------------------------------------------------------- helpers

/** Wraps fetch with consistent error handling — throws the server's error message if !res.ok. */
const request = async <T>(url: string, init: RequestInit = {}): Promise<T> => {
  let res: Response;
  try {
    res = await fetch(url, {
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

/** Build the Authorization header from the token in localStorage (or empty). */
const authHeaders = (): Record<string, string> => {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ----------------------------------------------------------------- auth

export const signup = (name: string, email: string, password: string): Promise<AuthResponse> => {
  if (USE_MOCK_DATA) return mockSignup(name, email, password);
  return request<AuthResponse>(`${BASE}/auth/signup`, {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
};

export const login = (email: string, password: string): Promise<AuthResponse> => {
  if (USE_MOCK_DATA) return mockLogin(email, password);
  return request<AuthResponse>(`${BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
};

// ----------------------------------------------------------------- posts

export const fetchPosts = (opts: { limit?: number; offset?: number } = {}): Promise<Post[]> => {
  if (USE_MOCK_DATA) return mockFetchPosts(opts);
  const sp = new URLSearchParams();
  if (typeof opts.limit === "number") sp.set("limit", String(opts.limit));
  if (typeof opts.offset === "number") sp.set("offset", String(opts.offset));
  return request<Post[]>(`${BASE}/posts?${sp.toString()}`);
};

export const createPost = (payload: {
  title: string;
  body: string;
  defendant: string;
  charges?: string[];
}): Promise<Post> => {
  if (USE_MOCK_DATA) return mockCreatePost(payload);
  return request<Post>(`${BASE}/posts`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
};

// ----------------------------------------------------------------- users

export const fetchUsers = (opts: { search?: string; limit?: number; offset?: number } = {}): Promise<UserListItem[]> => {
  if (USE_MOCK_DATA) return mockFetchUsers(opts);
  const sp = new URLSearchParams();
  if (opts.search) sp.set("search", opts.search);
  if (typeof opts.limit === "number") sp.set("limit", String(opts.limit));
  if (typeof opts.offset === "number") sp.set("offset", String(opts.offset));
  return request<UserListItem[]>(`${BASE}/users?${sp.toString()}`);
};

export const fetchUserProfile = (id: number): Promise<UserProfileResponse> => {
  if (USE_MOCK_DATA) return mockFetchUserProfile(id);
  return request<UserProfileResponse>(`${BASE}/users/${id}`);
};

// ----------------------------------------------------------- session helpers

export const getStoredUser = (): User | null => {
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
};

export const isLoggedIn = (): boolean => !!localStorage.getItem("token");

export const saveSession = (token: string, user: User): void => {
  localStorage.setItem("token", token);
  localStorage.setItem("user", JSON.stringify(user));
  // Notify same-tab listeners (the native "storage" event only fires for OTHER tabs).
  window.dispatchEvent(new Event("auth-change"));
};

export const clearSession = (): void => {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.dispatchEvent(new Event("auth-change"));
};
