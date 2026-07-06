import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  GitBranch,
  Loader2,
  Rocket,
  TrendingUp,
} from "lucide-react";
import { fetchOverview, type OverviewReport } from "../lib/reports";
import { Bar, ENV_COLORS, WORK_COLORS } from "./DeliveryPanel";

function Kpi({ value, label, tone = "" }: { value: string | number; label: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
      <div className={"text-2xl font-bold " + (tone || "text-ops-text")}>{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-ops-muted">{label}</div>
    </div>
  );
}

export function OverviewPanel() {
  const [o, setO] = useState<OverviewReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setO(await fetchOverview());
      setLoading(false);
    })();
  }, []);

  if (loading)
    return (
      <div className="py-12 text-center text-ops-muted">
        <Loader2 size={20} className="mx-auto animate-spin" />
        <p className="mt-2 text-xs">Building the executive summary…</p>
      </div>
    );
  if (!o) return <p className="py-12 text-center text-sm text-ops-muted">Couldn't load the overview.</p>;

  const h = o.headline;
  const issues = h.failing_pods + h.failed_pipelines;
  const work = o.work_breakdown || {};
  const workTotal = Object.values(work).reduce((a, b) => a + b, 0) || 1;
  const maxDay = Math.max(1, ...o.per_day.map((x) => x.total));
  const maxProd = Math.max(1, ...o.products.map((p) => p.deploys));

  return (
    <div className="overflow-y-auto p-5">
      {/* health banner */}
      <div
        className={
          "mb-4 flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm " +
          (issues === 0
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : "border-amber-500/30 bg-amber-500/10 text-amber-200")
        }
      >
        {issues === 0 ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        {issues === 0
          ? "All clear — no failing pods or pipelines right now."
          : `${issues} issue${issues > 1 ? "s" : ""} need attention: ${h.failing_pods} failing pod${h.failing_pods !== 1 ? "s" : ""}, ${h.failed_pipelines} failed pipeline${h.failed_pipelines !== 1 ? "s" : ""}.`}
        <span className="ml-auto text-[11px] opacity-70">
          {o.group} · {o.headline.projects_scanned} projects · {o.window_days}d
        </span>
      </div>

      {/* KPI grid */}
      <div className="mb-5 grid grid-cols-4 gap-3">
        <Kpi value={h.deploys_window} label={`Deploys / ${o.window_days}d`} />
        <Kpi value={`${h.success_rate}%`} label="Success rate" tone="text-emerald-400" />
        <Kpi value={h.deploys_today} label="Deploys today" tone="text-ops-accent" />
        <Kpi value={h.features + h.bugfixes} label="Features + fixes" />
        <Kpi value={h.features} label="Features" tone="text-[#6d7cff]" />
        <Kpi value={h.bugfixes} label="Bug fixes" tone="text-[#ef4444]" />
        <Kpi value={h.failing_pods} label="Failing pods" tone={h.failing_pods ? "text-amber-400" : "text-ops-text"} />
        <Kpi value={h.failed_pipelines} label="Failed pipelines" tone={h.failed_pipelines ? "text-red-400" : "text-ops-text"} />
      </div>

      {/* env + work breakdown */}
      <div className="mb-5 grid grid-cols-2 gap-4">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">By environment</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.keys(o.by_env).length === 0 && <span className="text-xs text-ops-muted">—</span>}
            {Object.entries(o.by_env).map(([e, n]) => (
              <div key={e} className="flex items-center gap-1.5 rounded-lg border border-ops-border bg-ops-panel/50 px-2 py-1 text-xs">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: ENV_COLORS[e] || ENV_COLORS.OTHER }} />
                {e} <span className="text-ops-muted">{n}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">Work shipped (AI)</div>
          <div className="mb-1 flex h-2.5 w-full overflow-hidden rounded-full bg-ops-bg">
            {Object.entries(work).map(([k, v]) => (
              <div key={k} style={{ width: `${(100 * v) / workTotal}%`, background: WORK_COLORS[k] || WORK_COLORS.other }} title={`${k}: ${v}`} />
            ))}
          </div>
          <div className="flex flex-wrap gap-2 text-[11px] text-ops-muted">
            {Object.entries(work).map(([k, v]) => (
              <span key={k} className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full" style={{ background: WORK_COLORS[k] || WORK_COLORS.other }} />
                {k} <span className="text-ops-text">{v}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* trend */}
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
        <TrendingUp size={12} /> Deployments per day
      </div>
      <div className="mb-5 space-y-1.5">
        {o.per_day.map((row) => (
          <div key={row.date} className="flex items-center gap-2">
            <span className="w-12 shrink-0 text-[11px] text-ops-muted">{row.date.slice(5)}</span>
            <div className="flex-1" style={{ width: `${(100 * row.total) / maxDay}%`, minWidth: "2%" }}>
              <Bar data={row.by_env} total={row.total} />
            </div>
            <span className="w-7 shrink-0 text-right text-[11px] font-medium">{row.total}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* product leaderboard */}
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
            <Rocket size={12} /> Top products by deploys
          </div>
          <div className="space-y-1.5">
            {o.products.slice(0, 8).map((p) => (
              <div key={p.product} className="flex items-center gap-2">
                <span className="w-28 shrink-0 truncate text-xs" title={p.product}>{p.product}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ops-bg">
                  <div className="h-full bg-gemini" style={{ width: `${(100 * p.deploys) / maxProd}%` }} />
                </div>
                <span className="w-6 shrink-0 text-right text-[11px] font-medium">{p.deploys}</span>
              </div>
            ))}
          </div>
        </div>

        {/* needs attention */}
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
            <AlertTriangle size={12} /> Needs attention
          </div>
          <div className="space-y-1.5">
            {o.attention.pods.length === 0 && o.attention.pipelines.length === 0 && (
              <p className="text-xs text-ops-muted">Nothing — all healthy. 🎉</p>
            )}
            {o.attention.pods.map((p) => (
              <div key={`${p.namespace}/${p.pod}`} className="flex items-center gap-2 rounded-lg border border-ops-border bg-ops-panel/50 px-2.5 py-1.5 text-[11px]">
                <Boxes size={12} className="shrink-0 text-amber-400" />
                <span className="min-w-0 flex-1 truncate" title={`${p.namespace}/${p.pod}`}>{p.pod}</span>
                <span className="shrink-0 text-red-300">{p.reason}</span>
                <span className="shrink-0 text-ops-muted">{p.restarts}×</span>
              </div>
            ))}
            {o.attention.pipelines.map((p) => (
              <div key={p.project} className="flex items-center gap-2 rounded-lg border border-ops-border bg-ops-panel/50 px-2.5 py-1.5 text-[11px]">
                <GitBranch size={12} className="shrink-0 text-red-400" />
                <span className="min-w-0 flex-1 truncate" title={p.project}>{p.project.replace(/^DOL\//, "")}</span>
                <span className="shrink-0 text-ops-muted">{p.count} failed</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
