import { useRef, useState } from "react";
import { Loader2, Send, Wrench } from "lucide-react";
import { streamChat } from "../../lib/api";
import { Markdown } from "../Markdown";
import { useDashColors } from "./DashTheme";

interface Msg { role: "user" | "assistant"; content: string; tools?: string[] }

const SUGGESTIONS = [
  "Which assets are least compliant in dev?",
  "Why did control LIN-5.1.1 fail on router-01?",
  "How many SSH controls pass on router-01?",
  "Summarize AWS compliance gaps",
];

export function GrcChat() {
  const C = useDashColors();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  const scroll = () => requestAnimationFrame(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  });

  const send = (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    const history: Msg[] = [...msgs, { role: "user", content: q }];
    setMsgs([...history, { role: "assistant", content: "", tools: [] }]);
    setBusy(true);
    scroll();
    const update = (fn: (m: Msg) => Msg) =>
      setMsgs((cur) => cur.map((m, i) => (i === cur.length - 1 ? fn(m) : m)));
    streamChat(
      { messages: history.map((m) => ({ role: m.role, content: m.content })), mode: "auto" },
      {
        onToolCall: (name) => { update((m) => ({ ...m, tools: [...(m.tools || []), name] })); scroll(); },
        onToken: (t) => { update((m) => ({ ...m, content: m.content + t })); scroll(); },
        onError: (e) => { update((m) => ({ ...m, content: m.content + `\n\n_${e}_` })); setBusy(false); },
        onDone: () => { setBusy(false); scroll(); },
      },
    );
  };

  return (
    <div className="flex flex-col" style={{ height: 380 }}>
      <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {msgs.length === 0 && (
          <div className="py-4">
            <p className="mb-2 text-[12px]" style={{ color: C.muted }}>Ask anything about your compliance data — it queries the live ELK scans.</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full px-2.5 py-1 text-[11px]" style={{ border: `1px solid ${C.border}`, color: C.accent }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
            <div className="max-w-[85%] rounded-2xl px-3 py-2 text-[13px]"
              style={m.role === "user"
                ? { background: C.accent, color: "#fff" }
                : { background: C.bg, color: C.text, border: `1px solid ${C.border}` }}>
              {m.role === "assistant" && m.tools && m.tools.length > 0 && (
                <div className="mb-1 flex items-center gap-1 text-[10px]" style={{ color: C.muted }}>
                  <Wrench size={10} /> {Array.from(new Set(m.tools)).join(", ")}
                </div>
              )}
              {m.role === "assistant"
                ? (m.content ? <div className="dash-analysis"><Markdown content={m.content} /></div>
                    : <span className="flex items-center gap-1.5" style={{ color: C.muted }}><Loader2 size={12} className="animate-spin" /> thinking…</span>)
                : m.content}
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="mt-2 flex items-center gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about compliance…"
          className="flex-1 rounded-xl px-3 py-2 text-[13px] outline-none"
          style={{ background: C.bg, border: `1px solid ${C.border}`, color: C.text }} />
        <button type="submit" disabled={busy || !input.trim()} className="flex items-center justify-center rounded-xl px-3 py-2 text-white disabled:opacity-40" style={{ background: C.accent }}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
        </button>
      </form>
    </div>
  );
}
