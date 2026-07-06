import { useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2, Paperclip, Square } from "lucide-react";
import clsx from "clsx";
import { uploadDocument } from "../lib/docs";
import type { RequestMode } from "../lib/types";

interface Props {
  streaming: boolean;
  mode: RequestMode;
  onModeChange: (m: RequestMode) => void;
  onSend: (text: string) => void;
  onStop: () => void;
}

const MODES: { id: RequestMode; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "ops-chat", label: "Chat" },
  { id: "ops-think", label: "Think" },
  { id: "ops-code", label: "Code" },
  { id: "ops-docs", label: "Docs" },
];

export function Composer({
  streaming,
  mode,
  onModeChange,
  onSend,
  onStop,
}: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setUploadNote(null);
    try {
      const doc = await uploadDocument(file);
      setUploadNote(`Indexed "${doc.filename}" — ${doc.chunk_count} chunks. Ask in Docs mode.`);
      onModeChange("ops-docs");
      setTimeout(() => setUploadNote(null), 5000);
    } catch (err) {
      setUploadNote((err as Error).message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  // auto-resize the textarea up to a max height
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [text]);

  const submit = () => {
    if (!text.trim() || streaming) return;
    onSend(text);
    setText("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4">
      <div className="mb-2 flex items-center gap-1">
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => onModeChange(m.id)}
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-medium transition",
              mode === m.id
                ? "bg-gemini text-white shadow-glow"
                : "glass text-ops-muted hover:text-ops-text",
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      {uploadNote && (
        <div className="mb-2 rounded-lg border border-ops-border bg-ops-panel px-3 py-1.5 text-xs text-ops-muted">
          {uploadNote}
        </div>
      )}
      <div className="glass flex items-end gap-2 rounded-2xl p-2 shadow-glow transition-shadow duration-300 focus-within:shadow-glow-lg">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt,.md,.markdown,.log,.yaml,.yml,.json,.csv"
          className="hidden"
          onChange={onFile}
        />
        <button
          type="button"
          title="Attach a document (PDF, txt, md…)"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="mb-1 rounded-lg p-2 text-ops-muted transition hover:text-ops-text disabled:opacity-50"
        >
          {uploading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Paperclip size={18} />
          )}
        </button>

        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Message OpsGPT…"
          className="max-h-[200px] flex-1 resize-none bg-transparent py-2 text-[0.95rem] text-ops-text placeholder:text-ops-muted focus:outline-none"
        />

        {streaming ? (
          <button
            onClick={onStop}
            title="Stop"
            className="mb-0.5 rounded-lg bg-ops-text p-2 text-ops-bg transition hover:opacity-90"
          >
            <Square size={18} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!text.trim()}
            title="Send"
            className="mb-0.5 rounded-xl bg-gemini p-2 text-white shadow-glow transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30 disabled:shadow-none"
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-[11px] text-ops-muted">
        OpsGPT can make mistakes. Verify important info. Enter to send,
        Shift+Enter for newline.
      </p>
    </div>
  );
}
