import type { Conversation } from "./types";

const KEY = "opsgpt.conversations.v1";

// Phase 1 persists conversation history in localStorage. Phase 2 moves this to
// PostgreSQL behind authenticated API calls; the UI contract stays the same.
export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Conversation[];
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(conversations));
  } catch {
    /* quota / private mode — ignore */
  }
}

export function uid(): string {
  return (
    Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  );
}
