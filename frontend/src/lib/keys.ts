import { authedFetch } from "./auth";

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  revoked: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export async function listKeys(): Promise<ApiKey[]> {
  const res = await authedFetch("/keys");
  if (!res.ok) return [];
  return (await res.json()) as ApiKey[];
}

export async function createKey(name: string): Promise<ApiKeyCreated> {
  const res = await authedFetch("/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create key");
  return (await res.json()) as ApiKeyCreated;
}

export async function revokeKey(id: string): Promise<void> {
  await authedFetch(`/keys/${id}`, { method: "DELETE" });
}
