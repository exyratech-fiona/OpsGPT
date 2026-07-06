import { authedFetch } from "./auth";
import type { AdminStats, AdminUser } from "./types";

export async function fetchStats(): Promise<AdminStats | null> {
  const res = await authedFetch("/admin/stats");
  if (!res.ok) return null;
  return (await res.json()) as AdminStats;
}

export async function fetchUsers(): Promise<AdminUser[]> {
  const res = await authedFetch("/admin/users");
  if (!res.ok) return [];
  return (await res.json()) as AdminUser[];
}

export async function createUser(
  email: string,
  password: string,
  role: string,
  daily_token_limit = 0,
): Promise<{ ok: boolean; error?: string }> {
  const res = await authedFetch("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, role, daily_token_limit }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    return { ok: false, error: (d as { detail?: string }).detail || `Error ${res.status}` };
  }
  return { ok: true };
}

export async function setUserRole(id: string, role: string): Promise<void> {
  await authedFetch(`/admin/users/${id}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
}

export async function setUserActive(id: string, is_active: boolean): Promise<void> {
  await authedFetch(`/admin/users/${id}/active`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active }),
  });
}

export async function setUserLimit(id: string, daily_token_limit: number): Promise<void> {
  await authedFetch(`/admin/users/${id}/limit`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ daily_token_limit }),
  });
}
