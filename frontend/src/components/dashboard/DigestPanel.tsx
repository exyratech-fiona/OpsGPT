import { useState } from "react";
import { Loader2, Mail, Sparkles } from "lucide-react";
import { sendDigest, streamDigest } from "../../lib/reports";
import { Markdown } from "../Markdown";
import { useAuth } from "../../context/AuthContext";
import { useDashColors } from "./DashTheme";
import { Card } from "./ui";

export function DigestPanel() {
  const C = useDashColors();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sendMsg, setSendMsg] = useState<string | null>(null);

  const gen = async () => {
    setText("");
    setStreaming(true);
    setSendMsg(null);
    await streamDigest((t) => setText((p) => p + t));
    setStreaming(false);
  };
  const send = async () => {
    setSendMsg("Emailing…");
    const r = await sendDigest();
    setSendMsg(r ? (r.ok ? `Emailed ✓ — ${r.message}` : `Email failed: ${r.message}`) : "Email failed — configure SMTP first.");
  };

  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide" style={{ color: C.accent }}>
          <Sparkles size={14} /> Weekly AI digest
        </div>
        <div className="flex gap-2">
          <button onClick={gen} disabled={streaming} className="rounded-lg px-2.5 py-1 text-[12px] font-medium text-white disabled:opacity-50" style={{ background: C.accent }}>
            {streaming ? "Generating…" : text ? "Regenerate" : "Generate"}
          </button>
          {isAdmin && (
            <button onClick={send} className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[12px]" style={{ border: `1px solid ${C.border}`, color: C.text }}>
              <Mail size={12} /> Email to team
            </button>
          )}
        </div>
      </div>
      {sendMsg && <p className="mb-2 text-[11px]" style={{ color: C.muted }}>{sendMsg}</p>}
      {text ? (
        <div className="dash-analysis text-[13px]"><Markdown content={text} /></div>
      ) : streaming ? (
        <div className="flex items-center gap-2 py-3 text-sm" style={{ color: C.muted }}><Loader2 size={14} className="animate-spin" /> Writing the executive summary…</div>
      ) : (
        <p className="text-[12px]" style={{ color: C.muted }}>
          Generate an AI-written executive summary of this period's delivery &amp; reliability — paste into a report, or email it to the team weekly (admins can configure the schedule).
        </p>
      )}
    </Card>
  );
}
