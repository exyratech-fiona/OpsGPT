import { useEffect, useState } from "react";
import { AlertTriangle, Boxes, CheckCircle2, GitBranch, Lightbulb, Loader2, Users } from "lucide-react";
import { fetchOverview, type OverviewReport } from "../../lib/reports";
import { insights } from "./theme";
import { useDashColors } from "./DashTheme";
import { Card, Kpi } from "./ui";
import { CustomerCard } from "./CustomerCard";
import { DigestPanel } from "./DigestPanel";
import { DayTrend, EnvBar, PeopleBar, ProductBar, WorkPie } from "./Charts";

export function DashOverview() {
  const C = useDashColors();
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
      <div className="py-20 text-center" style={{ color: C.muted }}>
        <Loader2 size={22} className="mx-auto animate-spin" />
        <p className="mt-2 text-sm">Building the executive summary…</p>
      </div>
    );
  if (!o) return <p className="py-20 text-center text-sm" style={{ color: C.muted }}>Couldn't load the overview.</p>;

  const h = o.headline;
  const issues = h.failing_pods + h.failed_pipelines;
  const tips = insights(o);
  const toneColor = { good: C.ok, warn: C.warn, bad: C.danger };
  const fmtDur = (hr: number | null) => (hr == null ? "—" : hr < 48 ? `${hr}h` : `${(hr / 24).toFixed(1)}d`);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2.5 rounded-2xl px-4 py-3 text-sm font-medium"
        style={{
          background: issues === 0 ? (C.dark ? "#0f2a1d" : "#ecfdf3") : (C.dark ? "#2a2410" : "#fffbeb"),
          color: issues === 0 ? C.ok : C.warn,
          border: `1px solid ${issues === 0 ? (C.dark ? "#1f5c3f" : "#bbf7d0") : (C.dark ? "#6b5510" : "#fde68a")}`,
        }}>
        {issues === 0 ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
        {issues === 0
          ? "All clear — no failing pods or pipelines right now."
          : `${issues} issue${issues > 1 ? "s" : ""} need attention: ${h.failing_pods} failing pod${h.failing_pods !== 1 ? "s" : ""}, ${h.failed_pipelines} failed pipeline${h.failed_pipelines !== 1 ? "s" : ""}.`}
        <span className="ml-auto text-[12px] font-normal opacity-75">{o.group} · {h.projects_scanned} projects · {o.window_days}d</span>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi value={h.real_changes} label="Changes to real envs" tone={C.ok} />
        <Kpi value={`${h.success_rate}%`} label="Deploy success" tone={C.ok} />
        <Kpi value={`${h.change_failure_rate}%`} label="Change failure rate" tone={h.change_failure_rate > 20 ? C.danger : C.warn} />
        <Kpi value={issues} label="Needs attention" tone={issues ? C.danger : C.text} />
      </div>

      <Card title="DORA delivery-performance metrics">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi value={`${(h.deploys_window / o.window_days).toFixed(1)}/day`} label="Deployment frequency" />
          <Kpi value={fmtDur(h.lead_time_hours)} label="Lead time (commit→real env)" tone={C.accent} />
          <Kpi value={`${h.change_failure_rate}%`} label="Change failure rate" tone={h.change_failure_rate > 20 ? C.danger : C.warn} />
          <Kpi value={fmtDur(h.mttr_hours)} label="Time to restore (MTTR)" tone={C.ok} />
        </div>
        <p className="mt-2 text-[11px]" style={{ color: C.muted }}>
          The four industry-standard DORA metrics. Lead time = commit authored → reached a real environment; MTTR = median time from a failed deploy to the next success.
        </p>
      </Card>

      <Card>
        <div className="mb-3 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide" style={{ color: C.accent }}>
          <Lightbulb size={14} /> Executive insights
        </div>
        <ul className="space-y-2">
          {tips.map((t, i) => (
            <li key={i} className="flex items-start gap-2 text-[13.5px]" style={{ color: C.text }}>
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: toneColor[t.tone] }} />
              {t.text}
            </li>
          ))}
        </ul>
      </Card>

      <DigestPanel />

      <CustomerCard customers={o.per_customer} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Promotion funnel — distinct changes per environment"><EnvBar by_env={o.funnel} /></Card>
        <Card title="Work shipped (AI-classified)"><WorkPie work={o.work_breakdown} /></Card>
      </div>
      <Card title="Deployment trend (per day)"><DayTrend per_day={o.per_day} /></Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Top products by deployments"><ProductBar products={o.products} /></Card>
        <Card>
          <div className="mb-3 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide" style={{ color: C.muted }}>
            <Users size={13} /> Promotions to real environments
          </div>
          <PeopleBar people={o.top_deployers} />
          <p className="mt-2 text-[11px]" style={{ color: C.muted }}>
            Who promoted the most distinct changes to SIT/DEMO/UAT/PROD (DEV auto-deploys excluded). Full list on the Delivery tab.
          </p>
        </Card>
      </div>

      <Card title="Needs attention">
        <div className="space-y-2">
          {o.attention.pods.length === 0 && o.attention.pipelines.length === 0 && (
            <p className="text-sm" style={{ color: C.muted }}>Nothing — all healthy. 🎉</p>
          )}
          {o.attention.pods.map((p) => (
            <div key={`${p.namespace}/${p.pod}`} className="rounded-xl px-3 py-2 text-[12px]" style={{ background: C.dark ? "#2a1416" : "#fef2f2" }}>
              <div className="flex items-center gap-2">
                <Boxes size={13} style={{ color: C.warn }} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate" style={{ color: C.text }} title={`${p.namespace}/${p.pod}`}>{p.pod}</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 pl-5 text-[11px]">
                <span className="rounded px-1.5 py-0.5" style={{ background: C.card, color: C.muted }}>{p.namespace}</span>
                <span style={{ color: C.danger }}>{p.reason}</span>
                <span style={{ color: C.muted }}>{p.restarts.toLocaleString()} restarts</span>
              </div>
            </div>
          ))}
          {o.attention.pipelines.map((p) => (
            <div key={p.project} className="flex items-center gap-2 rounded-xl px-3 py-2 text-[12px]" style={{ background: C.dark ? "#2a1f12" : "#fff7ed" }}>
              <GitBranch size={13} style={{ color: C.danger }} className="shrink-0" />
              <span className="min-w-0 flex-1 truncate" style={{ color: C.text }} title={p.project}>{p.project.replace(/^DOL\//, "")}</span>
              <span style={{ color: C.muted }}>{p.count} failed</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
