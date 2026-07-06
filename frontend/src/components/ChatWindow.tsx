import { useEffect, useRef } from "react";
import { RefreshCw } from "lucide-react";
import type { Conversation } from "../lib/types";
import { Message } from "./Message";
import { ThinkingDots } from "./ThinkingDots";

interface Props {
  conversation: Conversation | null;
  streaming: boolean;
  onRegenerate: () => void;
  onPick: (text: string) => void;
}

const SUGGESTIONS = [
  "Write a multi-stage Dockerfile for a FastAPI app",
  "Explain Kubernetes liveness vs readiness probes",
  "Terraform module for an AWS VPC with public/private subnets",
  "Why is my pod stuck in CrashLoopBackOff?",
];

export function ChatWindow({
  conversation,
  streaming,
  onRegenerate,
  onPick,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const messages = conversation?.messages ?? [];

  // auto-scroll to the newest content while streaming
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streaming]);

  const last = messages[messages.length - 1];
  const waitingFirstToken =
    streaming &&
    last?.role === "assistant" &&
    last.content === "" &&
    !last.reasoning &&
    !(last.toolSteps && last.toolSteps.length > 0);

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-4">
        <div className="mb-4 flex h-16 w-16 animate-glow-pulse items-center justify-center rounded-2xl bg-gemini text-3xl font-bold text-white shadow-glow-lg">
          O
        </div>
        <h1 className="mb-1 text-3xl font-bold tracking-tight text-gradient">
          How can I help you ship today?
        </h1>
        <p className="mb-8 text-sm text-ops-muted">
          OpsGPT — your self-hosted DevOps assistant
        </p>
        <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onPick(s)}
              className="glass rounded-xl px-4 py-3 text-left text-sm text-ops-text transition hover:shadow-glow"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="pb-6">
        {messages.map((m, i) => (
          <Message
            key={m.id}
            message={m}
            streaming={
              streaming && i === messages.length - 1 && m.role === "assistant"
            }
          />
        ))}
        {waitingFirstToken && <ThinkingDots />}

        {!streaming && last?.role === "assistant" && !last.error && (
          <div className="mx-auto max-w-3xl px-4">
            <button
              onClick={onRegenerate}
              className="flex items-center gap-1.5 rounded-lg border border-ops-border px-3 py-1.5 text-xs text-ops-muted transition hover:text-ops-text"
            >
              <RefreshCw size={13} />
              Regenerate
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
