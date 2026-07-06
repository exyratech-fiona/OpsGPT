import { useState } from "react";
import {
  Check,
  Copy,
  FileText,
  Loader2,
  Terminal,
  TriangleAlert,
  Zap,
} from "lucide-react";
import clsx from "clsx";
import type { ChatMessage } from "../lib/types";
import { Markdown } from "./Markdown";

interface Props {
  message: ChatMessage;
  streaming?: boolean;
}

export function Message({ message, streaming }: Props) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="animate-fade-in py-5">
      <div className="mx-auto flex max-w-3xl gap-4 px-4">
        <div
          className={clsx(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold",
            isUser
              ? "bg-ops-border text-ops-text"
              : "bg-gemini text-white shadow-glow",
          )}
          aria-hidden
        >
          {isUser ? "You" : "Ops"}
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-sm font-medium text-ops-text">
              {isUser ? "You" : "OpsGPT"}
            </span>
            {!isUser && message.model && (
              <span className="rounded border border-ops-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ops-muted">
                {message.model}
              </span>
            )}
          </div>

          {message.error ? (
            <div className="flex items-center gap-2 rounded-md border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              <TriangleAlert size={15} />
              {message.content}
            </div>
          ) : isUser ? (
            <div className="whitespace-pre-wrap break-words text-[0.95rem] leading-7">
              {message.content}
            </div>
          ) : (
            <div className="break-words text-[0.95rem]">
              {message.toolSteps && message.toolSteps.length > 0 && (
                <div className="mb-3 space-y-1.5">
                  {message.toolSteps.map((step, i) => (
                    <details
                      key={i}
                      className="rounded-lg border border-ops-border bg-ops-panel/50"
                    >
                      <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-1.5 text-ops-muted hover:text-ops-text">
                        <Terminal size={13} className="shrink-0 text-ops-accent" />
                        <span className="truncate font-mono text-xs">
                          {step.name}(
                          {Object.entries(step.arguments ?? {})
                            .map(([k, v]) => `${k}=${String(v)}`)
                            .join(", ")}
                          )
                        </span>
                        {step.result === undefined && (
                          <Loader2 size={12} className="ml-auto shrink-0 animate-spin" />
                        )}
                      </summary>
                      {step.result !== undefined && (
                        <pre className="max-h-60 overflow-auto whitespace-pre-wrap border-t border-ops-border px-3 py-2 font-mono text-[0.72rem] leading-5 text-ops-muted">
                          {step.result}
                        </pre>
                      )}
                    </details>
                  ))}
                </div>
              )}
              {message.reasoning && (
                <details className="mb-3 rounded-lg border border-ops-border bg-ops-panel/50 text-sm">
                  <summary className="cursor-pointer select-none px-3 py-2 text-ops-muted hover:text-ops-text">
                    Thinking…
                  </summary>
                  <div className="whitespace-pre-wrap border-t border-ops-border px-3 py-2 font-mono text-[0.8rem] leading-6 text-ops-muted">
                    {message.reasoning}
                  </div>
                </details>
              )}
              <Markdown content={message.content} />
              {streaming && (
                <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-blink bg-ops-text align-middle" />
              )}
              {message.citations && message.citations.length > 0 && (
                <div className="mt-3 border-t border-ops-border pt-2">
                  <div className="mb-1.5 text-xs font-medium text-ops-muted">
                    Sources
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {message.citations.map((c) => (
                      <span
                        key={c.index}
                        className="flex items-center gap-1 rounded-md border border-ops-border bg-ops-panel px-2 py-1 text-[11px] text-ops-muted"
                        title={`relevance ${c.score}`}
                      >
                        <FileText size={11} className="text-ops-accent" />[{c.index}]{" "}
                        {c.filename}
                        {c.page ? ` · p.${c.page}` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!isUser && !streaming && !message.error && message.content && (
            <div className="mt-2 flex items-center gap-3">
              <button
                onClick={copy}
                className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ops-muted transition hover:text-ops-text"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                {copied ? "Copied" : "Copy"}
              </button>
              {message.stats && (
                <span
                  className="flex items-center gap-1 text-[11px] text-ops-muted"
                  title="Generation speed for this response"
                >
                  <Zap size={11} className="text-ops-accent" />
                  {message.stats.tokens} tokens · {message.stats.tps} tok/s
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
