import { refreshTokens } from "./auth";
import type { Citation, ModeInfo, RequestMode, StreamEvent } from "./types";

const API_BASE = "/api";

export interface StreamHandlers {
  onMeta?: (mode: string, model: string, displayName: string) => void;
  onReasoning?: (text: string) => void;
  onToolCall?: (name: string, args: Record<string, unknown>) => void;
  onToolResult?: (name: string, result: string) => void;
  onCitations?: (items: Citation[]) => void;
  onStats?: (tokens: number, tps: number) => void;
  onToken: (text: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

/**
 * Stream a chat completion via SSE.
 *
 * EventSource only supports GET, so we POST and parse the SSE frames off the
 * fetch ReadableStream ourselves. Returns the AbortController so the caller can
 * implement a Stop button.
 */
export function streamChat(
  params: {
    messages: { role: "user" | "assistant"; content: string }[];
    mode: RequestMode;
  },
  handlers: StreamHandlers,
): AbortController {
  const controller = new AbortController();

  const body = JSON.stringify(params);
  const doFetch = () =>
    fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body,
      signal: controller.signal,
    });

  (async () => {
    try {
      let res = await doFetch();
      // access token expired -> refresh once and retry
      if (res.status === 401 && (await refreshTokens())) {
        res = await doFetch();
      }
      if (res.status === 401) {
        handlers.onError?.("Session expired. Please log in again.");
        return;
      }
      if (!res.ok || !res.body) {
        handlers.onError?.(`Server error (${res.status})`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        let sep: number;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const json = line.slice(5).trim();
          if (!json) continue;
          let evt: StreamEvent;
          try {
            evt = JSON.parse(json) as StreamEvent;
          } catch {
            continue;
          }
          switch (evt.type) {
            case "meta":
              handlers.onMeta?.(evt.mode, evt.model, evt.display_name);
              break;
            case "reasoning":
              handlers.onReasoning?.(evt.content);
              break;
            case "tool_call":
              handlers.onToolCall?.(evt.name, evt.arguments);
              break;
            case "tool_result":
              handlers.onToolResult?.(evt.name, evt.result);
              break;
            case "citations":
              handlers.onCitations?.(evt.items);
              break;
            case "stats":
              handlers.onStats?.(evt.tokens, evt.tps);
              break;
            case "token":
              handlers.onToken(evt.content);
              break;
            case "error":
              handlers.onError?.(evt.message);
              break;
            case "done":
              handlers.onDone?.();
              break;
          }
        }
      }
      handlers.onDone?.();
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        handlers.onDone?.();
        return;
      }
      handlers.onError?.((err as Error).message || "Network error");
    }
  })();

  return controller;
}

export async function fetchModes(): Promise<ModeInfo[]> {
  try {
    const res = await fetch(`${API_BASE}/modes`);
    if (!res.ok) return [];
    return (await res.json()) as ModeInfo[];
  } catch {
    return [];
  }
}
