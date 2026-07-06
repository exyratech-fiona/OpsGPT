import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import { fetchExport, type ExportReport } from "../../lib/reports";
import { ReportDocument } from "../ReportDocument";
import { useDashColors } from "./DashTheme";
import { Card } from "./ui";

export function DashReport() {
  const C = useDashColors();
  const today = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const [from, setFrom] = useState(weekAgo);
  const [to, setTo] = useState(today);
  const [generating, setGenerating] = useState(false);
  const [doc, setDoc] = useState<ExportReport | null>(null);

  const generate = async () => {
    setGenerating(true);
    const r = await fetchExport(from, to);
    setGenerating(false);
    if (r) setDoc(r);
  };

  const inputCls = "mt-1 w-full rounded-lg px-2.5 py-2 text-sm outline-none";
  const inputStyle = { border: `1px solid ${C.border}`, color: C.text, background: "#fff" };

  return (
    <>
      <div className="mx-auto max-w-lg">
        <Card>
          <div className="mb-1 flex items-center gap-2 text-sm font-semibold" style={{ color: C.text }}>
            <FileDown size={16} style={{ color: C.accent }} /> Generate a board-ready report
          </div>
          <p className="mb-4 text-[12px]" style={{ color: C.muted }}>
            Choose a date range, generate a professional report, then download it as PDF to share with leadership.
          </p>
          <div className="mb-3 grid grid-cols-2 gap-3">
            <label className="text-[11px]" style={{ color: C.muted }}>
              From
              <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className={inputCls} style={inputStyle} />
            </label>
            <label className="text-[11px]" style={{ color: C.muted }}>
              To
              <input type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} className={inputCls} style={inputStyle} />
            </label>
          </div>
          <div className="mb-4 flex flex-wrap gap-2">
            {([["7d", 7], ["14d", 14], ["30d", 30]] as const).map(([lbl, days]) => (
              <button key={lbl} onClick={() => { setTo(today); setFrom(new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)); }}
                className="rounded-lg px-2.5 py-1 text-[11px]" style={{ border: `1px solid ${C.border}`, color: C.muted }}>
                Last {lbl}
              </button>
            ))}
          </div>
          <button onClick={generate} disabled={generating}
            className="flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium text-white disabled:opacity-50" style={{ background: C.accent }}>
            {generating ? <Loader2 size={15} className="animate-spin" /> : <FileDown size={15} />}
            {generating ? "Generating… (scanning GitLab + K8s)" : "Generate report"}
          </button>
        </Card>
      </div>
      {doc && <ReportDocument data={doc} onClose={() => setDoc(null)} />}
    </>
  );
}
