import { authedFetch, refreshTokens } from "./auth";
import type { DocumentInfo } from "./types";

export async function listDocuments(): Promise<DocumentInfo[]> {
  const res = await authedFetch("/documents");
  if (!res.ok) return [];
  return (await res.json()) as DocumentInfo[];
}

export async function uploadDocument(file: File): Promise<DocumentInfo> {
  const form = new FormData();
  form.append("file", file);
  // multipart: don't set Content-Type manually (browser sets the boundary).
  // Manual refresh-on-401 since authedFetch is JSON-oriented.
  const doFetch = () =>
    fetch("/api/documents", { method: "POST", credentials: "include", body: form });
  let res = await doFetch();
  if (res.status === 401 && (await refreshTokens())) res = await doFetch();
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail || `Upload failed (${res.status})`);
  }
  return (await res.json()) as DocumentInfo;
}

export async function deleteDocument(id: string): Promise<void> {
  await authedFetch(`/documents/${id}`, { method: "DELETE" });
}
