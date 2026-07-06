import { useState } from "react";
import { ArrowLeft, FileText, Loader2 } from "lucide-react";
import { releaseNotes, type ReleaseBacklog } from "../../lib/reports";
import { Markdown } from "../Markdown";
import { useDashColors } from "./DashTheme";
import { ENV_C } from "./theme";
import { Card } from "./ui";

export function ReleaseReadiness({ backlog }: { backlog: ReleaseBacklog[] }) {
  const C = useDashColors();
  const [notes, setNotes] = useState<{ title: string; text: string; streaming: boolean } | null>(null);

  const gen = async (b: ReleaseBacklog) => {
    if (!b.project_id) return;
    setNotes({ title: b.project.replace(/^DOL\//, ""), text: "", streaming: true });
    await releaseNotes(b.project_id, 14, (t) => setNotes((n) => (n ? { ...n, text: n.text + t } : n)));
    setNotes((n) => (n ? { ...n, streaming: false } : n));
  };

  if (notes)
    return (
      <Card>
        <button onClick={() => setNotes(null)} className="mb-3 flex items-center gap-1.5 text-[13px]" style={{ color: C.muted }}>
          <ArrowLeft size={15} /> Back to release readiness
        </button>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold" style={{ color: C.text }}>
          <FileText size={15} style={{ color: C.accent }} /> Release notes — {notes.title} (last 14 days)
        </div>
        {notes.text ? (
          <div className="dash-analysis text-[13.5px]"><Markdown content={notes.text} /></div>
        ) : (
          <div className="flex items-center gap-2 py-6 text-sm" style={{ color: C.muted }}>
            <Loader2 size={15} className="animate-spin" /> Reading merged MRs and writing notes…
          </div>
        )}
        {notes.streaming && notes.text && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse" style={{ background: C.accent }} />}
      </Card>
    );

  return (
    <Card title="Release readiness — changes in pre-prod awaiting PROD">
      <div className="max-h-80 overflow-y-auto">
        {backlog.length === 0 && <p className="text-sm" style={{ color: C.muted }}>Nothing pending — all promoted changes are in PROD. 🎉</p>}
        {backlog.map((b) => (
          <div key={b.project} className="flex items-center gap-2 py-1.5 text-[12.5px]" style={{ borderTop: `1px solid ${C.border}` }}>
            <span className="min-w-0 flex-1 truncate" style={{ color: C.text }} title={b.project}>{b.project.replace(/^DOL\//, "")}</span>
            <div className="hidden gap-1 sm:flex">
              {b.reached.map((e) => (
                <span key={e} className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: (ENV_C[e] || ENV_C.OTHER) + "22", color: ENV_C[e] || ENV_C.OTHER }}>{e}</span>
              ))}
            </div>
            <span className="w-14 text-right font-semibold" style={{ color: C.warn }}>{b.pending}</span>
            <button onClick={() => gen(b)} disabled={!b.project_id}
              className="shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium text-white disabled:opacity-40" style={{ background: C.accent }}>
              Notes
            </button>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px]" style={{ color: C.muted }}>
        Distinct changes that reached SIT/DEMO/UAT but <b>not PROD</b> in the window (your release backlog). Click <b>Notes</b> for AI-written release notes from that project's merged MRs.
      </p>
    </Card>
  );
}
