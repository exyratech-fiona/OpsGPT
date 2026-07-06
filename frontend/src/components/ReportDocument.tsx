import type { CSSProperties, ReactNode } from "react";
import { Download, X } from "lucide-react";
import type { ExportReport } from "../lib/reports";
import { ENV_COLORS } from "./DeliveryPanel";

const ENV_ORDER = ["DEV", "SIT", "DEMO", "UAT", "PREPROD", "PROD", "OTHER"];
const WORK_COLORS: Record<string, string> = {
  feature: "#4f46e5",
  bugfix: "#dc2626",
  task: "#d97706",
  chore: "#64748b",
  other: "#94a3b8",
};

function fmt(date: string) {
  try {
    return new Date(date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return date;
  }
}

function Kpi({ value, label, color = "#0f172a" }: { value: string | number; label: string; color?: string }) {
  return (
    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8 }} className="p-3 text-center">
      <div style={{ color, fontSize: 22, fontWeight: 700 }}>{value}</div>
      <div style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</div>
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 style={{ fontSize: 12, fontWeight: 700, color: "#4f46e5", textTransform: "uppercase", letterSpacing: ".06em", borderBottom: "2px solid #eef2ff", paddingBottom: 4, marginTop: 22, marginBottom: 10 }}>
      {children}
    </h2>
  );
}

const th: CSSProperties = { textAlign: "left", padding: "6px 8px", background: "#f8fafc", borderBottom: "1px solid #e2e8f0", fontSize: 11, color: "#475569" };
const td: CSSProperties = { padding: "6px 8px", borderBottom: "1px solid #f1f5f9", fontSize: 11.5, color: "#1e293b" };

export function ReportDocument({ data, onClose }: { data: ExportReport; onClose: () => void }) {
  const d = data.delivery;
  const t = d?.totals || ({} as DeliveryTotals);
  const work = d?.work_breakdown || {};
  const workTotal = Object.values(work).reduce((a, b) => a + b, 0) || 1;
  const envs = ENV_ORDER.filter((e) => (t.by_env || {})[e]);

  return (
    <div className="print-area fixed inset-0 z-[60] overflow-auto bg-slate-200">
      {/* toolbar (not printed) */}
      <div className="no-print sticky top-0 z-10 flex items-center justify-between bg-slate-900 px-4 py-2 text-white">
        <button onClick={onClose} className="flex items-center gap-1 rounded px-2 py-1 text-sm text-slate-300 hover:text-white">
          <X size={16} /> Close
        </button>
        <span className="text-xs text-slate-400">Report preview — use “Download PDF”, then choose “Save as PDF”.</span>
        <button onClick={() => window.print()} className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500">
          <Download size={15} /> Download PDF
        </button>
      </div>

      {/* paper */}
      <div className="paper mx-auto my-6 max-w-[820px] bg-white p-10 text-slate-800 shadow-xl" style={{ minHeight: 1040 }}>
        {/* header */}
        <div className="flex items-start justify-between border-b border-slate-200 pb-5">
          <div className="flex items-center gap-3">
            <div style={{ background: "linear-gradient(135deg,#6d7cff,#9b5cff,#ec5c9d)" }} className="flex h-11 w-11 items-center justify-center rounded-xl text-lg font-bold text-white">O</div>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>OpsGPT</div>
              <div style={{ fontSize: 13, color: "#475569" }}>Delivery &amp; Reliability Report</div>
            </div>
          </div>
          <div style={{ textAlign: "right", fontSize: 12, color: "#475569" }}>
            <div style={{ fontWeight: 600, color: "#0f172a" }}>{fmt(data.from)} — {fmt(data.to)}</div>
            <div>Group: {data.group}</div>
            <div>Generated: {new Date(data.generated_at).toLocaleString()}</div>
          </div>
        </div>

        {data.error && <p style={{ color: "#dc2626", marginTop: 16 }}>{data.error}</p>}

        {/* executive summary */}
        <SectionTitle>Executive summary</SectionTitle>
        <div className="grid grid-cols-3 gap-3">
          <Kpi value={t.real_changes ?? 0} label="Changes to real envs" color="#15803d" />
          <Kpi value={`${t.success_rate ?? 0}%`} label="Deploy success" color="#15803d" />
          <Kpi value={`${t.change_failure_rate ?? 0}%`} label="Change failure rate" color="#d97706" />
          <Kpi value={t.prod_changes ?? 0} label="Changes to PROD" color="#4f46e5" />
          <Kpi value={work.feature ?? 0} label="Features" color="#4f46e5" />
          <Kpi value={work.bugfix ?? 0} label="Bug fixes" color="#dc2626" />
          <Kpi value={d?.merged_mrs ?? 0} label="Merged MRs" />
          <Kpi value={t.deployments ?? 0} label="Deploy events (all envs)" />
          <Kpi value={data.failing_pods.length} label="Failing pods (now)" color={data.failing_pods.length ? "#d97706" : "#0f172a"} />
        </div>

        {/* deployments by environment */}
        <SectionTitle>Deployments by environment</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Environment</th><th style={th}>Deployments</th><th style={th}>Share</th></tr></thead>
          <tbody>
            {envs.length === 0 && <tr><td style={td} colSpan={3}>No deployments in range.</td></tr>}
            {envs.map((e) => {
              const n = t.by_env[e];
              const pct = Math.round((100 * n) / (t.deployments || 1));
              return (
                <tr key={e}>
                  <td style={td}><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 9, background: ENV_COLORS[e], marginRight: 6 }} />{e}</td>
                  <td style={td}>{n}</td>
                  <td style={td}>
                    <div style={{ background: "#f1f5f9", borderRadius: 6, height: 8, width: 160, display: "inline-block", verticalAlign: "middle" }}>
                      <div style={{ width: `${pct}%`, height: 8, borderRadius: 6, background: ENV_COLORS[e] }} />
                    </div> <span style={{ color: "#64748b" }}>{pct}%</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* work shipped */}
        <SectionTitle>Work shipped (AI-classified)</SectionTitle>
        <div style={{ display: "flex", height: 12, borderRadius: 6, overflow: "hidden", background: "#f1f5f9" }}>
          {Object.entries(work).map(([k, v]) => (
            <div key={k} style={{ width: `${(100 * v) / workTotal}%`, background: WORK_COLORS[k] || WORK_COLORS.other }} />
          ))}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 6, fontSize: 11.5, color: "#475569" }}>
          {Object.entries(work).map(([k, v]) => (
            <span key={k}><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 9, background: WORK_COLORS[k] || WORK_COLORS.other, marginRight: 5 }} />{k}: <b style={{ color: "#1e293b" }}>{v}</b></span>
          ))}
        </div>

        {/* per day */}
        <SectionTitle>Deployments per day</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Date</th>{envs.map((e) => <th key={e} style={th}>{e}</th>)}<th style={th}>Total</th></tr></thead>
          <tbody>
            {(d?.per_day || []).map((row) => (
              <tr key={row.date}>
                <td style={td}>{row.date}</td>
                {envs.map((e) => <td key={e} style={td}>{row.by_env[e] || ""}</td>)}
                <td style={{ ...td, fontWeight: 600 }}>{row.total}</td>
              </tr>
            ))}
            {(d?.per_day || []).length === 0 && <tr><td style={td} colSpan={envs.length + 2}>No deployments in range.</td></tr>}
          </tbody>
        </table>

        {/* top projects */}
        <SectionTitle>Top projects by deployments</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Project</th><th style={th}>Deployments</th><th style={th}>By env</th><th style={th}>MRs</th></tr></thead>
          <tbody>
            {(d?.per_project || []).slice(0, 20).map((p) => {
              const tot = Object.values(p.deploys).reduce((a, b) => a + b, 0);
              return (
                <tr key={p.project}>
                  <td style={td}>{p.project.replace(/^DOL\//, "")}</td>
                  <td style={td}>{tot}</td>
                  <td style={{ ...td, color: "#64748b" }}>{Object.entries(p.deploys).map(([e, n]) => `${e} ${n}`).join(" · ")}</td>
                  <td style={td}>{p.merged_mrs}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* promotions by developer */}
        <SectionTitle>Promotions to real environments by developer</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Developer</th><th style={th}>Real envs (SIT/DEMO/UAT/PROD)</th><th style={th}>DEV</th><th style={th}>Breakdown</th></tr></thead>
          <tbody>
            {(d?.top_deployers || []).filter((p) => p.real > 0 || p.dev > 0).slice(0, 25).map((p) => (
              <tr key={p.user}>
                <td style={td}>{p.user}</td>
                <td style={{ ...td, fontWeight: 600, color: p.real ? "#15803d" : "#94a3b8" }}>{p.real}</td>
                <td style={{ ...td, color: "#64748b" }}>{p.dev}</td>
                <td style={{ ...td, color: "#64748b" }}>{Object.entries(p.by_env).map(([e, n]) => `${e} ${n}`).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* failed pipelines */}
        <SectionTitle>Failed pipelines in range ({data.failed_pipelines.length})</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Project</th><th style={th}>Pipeline</th><th style={th}>Branch</th><th style={th}>When</th></tr></thead>
          <tbody>
            {data.failed_pipelines.length === 0 && <tr><td style={td} colSpan={4}>None. 🎉</td></tr>}
            {data.failed_pipelines.slice(0, 30).map((p) => (
              <tr key={`${p.project_id}-${p.pipeline_id}`}>
                <td style={td}>{p.project.replace(/^DOL\//, "")}</td>
                <td style={td}>#{p.pipeline_id}</td>
                <td style={{ ...td, color: "#64748b" }}>{p.ref}</td>
                <td style={td}>{new Date(p.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* failing pods */}
        <SectionTitle>Failing Kubernetes pods (current snapshot)</SectionTitle>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Namespace</th><th style={th}>Pod</th><th style={th}>Reason</th><th style={th}>Restarts</th></tr></thead>
          <tbody>
            {data.failing_pods.length === 0 && <tr><td style={td} colSpan={4}>None. 🎉</td></tr>}
            {data.failing_pods.slice(0, 30).map((p) => (
              <tr key={`${p.namespace}/${p.pod}`}>
                <td style={td}>{p.namespace}</td>
                <td style={td}>{p.pod}</td>
                <td style={{ ...td, color: "#dc2626" }}>{p.reason}</td>
                <td style={td}>{p.restarts}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ marginTop: 28, borderTop: "1px solid #e2e8f0", paddingTop: 10, fontSize: 10, color: "#94a3b8", textAlign: "center" }}>
          Generated by OpsGPT · Self-hosted AI for DevOps · {data.group} · {fmt(data.from)}–{fmt(data.to)}
        </div>
      </div>
    </div>
  );
}

type DeliveryTotals = {
  deployments: number;
  success_rate: number;
  change_failure_rate: number;
  real_changes: number;
  prod_changes: number;
  by_env: Record<string, number>;
};
