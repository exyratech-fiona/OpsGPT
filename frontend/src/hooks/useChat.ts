import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "../lib/api";
import {
  loadConversations,
  saveConversations,
  uid,
} from "../lib/storage";
import type { ChatMessage, Conversation, RequestMode } from "../lib/types";

function titleFrom(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 40 ? t.slice(0, 40) + "…" : t || "New chat";
}

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>(() =>
    loadConversations(),
  );
  const [activeId, setActiveId] = useState<string | null>(
    () => loadConversations()[0]?.id ?? null,
  );
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    saveConversations(conversations);
  }, [conversations]);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  const patchConversation = useCallback(
    (id: string, fn: (c: Conversation) => Conversation) => {
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? fn(c) : c)),
      );
    },
    [],
  );

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setActiveId(null);
  }, []);

  const selectChat = useCallback((id: string) => {
    abortRef.current?.abort();
    setActiveId(id);
  }, []);

  const deleteChat = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        setActiveId((cur) => (cur === id ? next[0]?.id ?? null : cur));
        return next;
      });
    },
    [],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  /** Core send: optionally seed the conversation from scratch. */
  const runCompletion = useCallback(
    (conversationId: string, history: ChatMessage[], mode: RequestMode) => {
      const assistantId = uid();
      const assistant: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
      };
      patchConversation(conversationId, (c) => ({
        ...c,
        messages: [...history, assistant],
        updatedAt: Date.now(),
      }));
      setStreaming(true);

      const controller = streamChat(
        {
          mode,
          // Only send non-empty, non-error turns (backend requires content >= 1).
          messages: history
            .filter((m) => !m.error && m.content.trim().length > 0)
            .map((m) => ({ role: m.role, content: m.content })),
        },
        {
          onMeta: (m, model) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId ? { ...msg, mode: m, model } : msg,
              ),
            })),
          onReasoning: (text) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, reasoning: (msg.reasoning ?? "") + text }
                  : msg,
              ),
            })),
          onToolCall: (name, args) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...msg,
                      toolSteps: [
                        ...(msg.toolSteps ?? []),
                        { name, arguments: args },
                      ],
                    }
                  : msg,
              ),
            })),
          onToolResult: (name, result) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) => {
                if (msg.id !== assistantId) return msg;
                const steps = [...(msg.toolSteps ?? [])];
                // attach the result to the most recent step of this tool
                for (let i = steps.length - 1; i >= 0; i--) {
                  if (steps[i].name === name && steps[i].result === undefined) {
                    steps[i] = { ...steps[i], result };
                    break;
                  }
                }
                return { ...msg, toolSteps: steps };
              }),
            })),
          onCitations: (items) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId ? { ...msg, citations: items } : msg,
              ),
            })),
          onStats: (tokens, tps) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId ? { ...msg, stats: { tokens, tps } } : msg,
              ),
            })),
          onToken: (text) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, content: msg.content + text }
                  : msg,
              ),
            })),
          onError: (message) =>
            patchConversation(conversationId, (c) => ({
              ...c,
              messages: c.messages.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, content: message, error: true }
                  : msg,
              ),
            })),
          onDone: () => setStreaming(false),
        },
      );
      abortRef.current = controller;
    },
    [patchConversation],
  );

  const send = useCallback(
    (text: string, mode: RequestMode) => {
      const content = text.trim();
      if (!content || streaming) return;

      const userMsg: ChatMessage = { id: uid(), role: "user", content };

      if (active) {
        const history = [...active.messages, userMsg];
        runCompletion(active.id, history, mode);
      } else {
        const id = uid();
        const conv: Conversation = {
          id,
          title: titleFrom(content),
          createdAt: Date.now(),
          updatedAt: Date.now(),
          messages: [userMsg],
        };
        setConversations((prev) => [conv, ...prev]);
        setActiveId(id);
        runCompletion(id, [userMsg], mode);
      }
    },
    [active, streaming, runCompletion],
  );

  const regenerate = useCallback(
    (mode: RequestMode) => {
      if (!active || streaming) return;
      // drop trailing assistant message, re-run from the last user turn
      const msgs = [...active.messages];
      while (msgs.length && msgs[msgs.length - 1].role === "assistant") {
        msgs.pop();
      }
      if (!msgs.length) return;
      runCompletion(active.id, msgs, mode);
    },
    [active, streaming, runCompletion],
  );

  return {
    conversations,
    active,
    activeId,
    streaming,
    send,
    stop,
    regenerate,
    newChat,
    selectChat,
    deleteChat,
  };
}
