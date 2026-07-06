// Auth API client. Access/refresh JWTs live in httpOnly cookies set by the
// backend, so they're invisible to JavaScript (XSS can't exfiltrate them). The
// browser attaches them automatically; we just send `credentials: "include"`.

const API = "/api";
const LEGACY_TOKEN_KEYS = ["opsgpt.access", "opsgpt.refresh"];

export interface User {
  id: string;
  email: string;
  role: "admin" | "user" | "guest";
  is_active: boolean;
  created_at: string;
}

/** Remove any tokens left in localStorage by the pre-cookie version of the app. */
export function purgeLegacyTokens(): void {
  try {
    LEGACY_TOKEN_KEYS.forEach((k) => localStorage.removeItem(k));
  } catch {
    /* storage may be unavailable */
  }
}

class AuthError extends Error {}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new AuthError((detail as { detail?: string }).detail || `Error ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function login(email: string, password: string): Promise<User> {
  return postJson<User>("/auth/login", { email, password });
}

export async function register(email: string, password: string): Promise<User> {
  return postJson<User>("/auth/register", { email, password });
}

/** Refresh the access cookie using the refresh cookie. Returns false if expired. */
export async function refreshTokens(): Promise<boolean> {
  try {
    const res = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });
  } catch {
    /* best effort */
  }
  purgeLegacyTokens();
}

/** fetch() that sends auth cookies and refreshes once on a 401. */
export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const opts = (): RequestInit => ({ ...init, credentials: "include" });
  let res = await fetch(`${API}${path}`, opts());
  if (res.status === 401 && (await refreshTokens())) {
    res = await fetch(`${API}${path}`, opts());
  }
  return res;
}

export async function fetchMe(): Promise<User | null> {
  let res = await fetch(`${API}/auth/me`, { credentials: "include" });
  if (res.status === 401 && (await refreshTokens())) {
    res = await fetch(`${API}/auth/me`, { credentials: "include" });
  }
  if (!res.ok) return null;
  return (await res.json()) as User;
}
