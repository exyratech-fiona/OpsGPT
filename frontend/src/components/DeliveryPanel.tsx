import { useEffect, useState } from "react";
import { Loader2, Rocket } from "lucide-react";
import { fetchDelivery, type DeliveryReport } from "../lib/reports";

export const ENV_COLORS: Record<string, string> = {
  DEV: "#6d7cff",
  SIT: "#f59e0b",
  DEMO: "#9b5cff",
  UAT: "#14b8a6",
  PREPROD: "#ec5c9d",
  PROD: "#15a06b",
  OTHER: "#64748b",
};
export const WORK_COLORS: Record<string, string> = {
  feature: "#6d7cff",
  bugfix: "#ef4444",
  task: "#f59e0b",
  chore: "#64748b",
  other: "#94a3b8",
};

export function Bar({ data, total }: { data: Record<string, number>; total: number }) {
  const order = ["DEV", "SIT", "DEMO", "UAT", "PREPROD", "PROD", "OTHER"];
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-ops-bg">
      {order
        .filter((e) => data[e])
        .map((e) => (
          <div
            key={e}
            style={{ width: `${(100 * data[e]) / (total || 1)}%`, background: ENV_COLORS[e] }}
            title={`${e}: ${data[e]}`}
          />
        ))}
    </div>
  );
}

export function DeliveryPanel() {
  const [d, setD] = useState<DeliveryReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setD(await fetchDelivery());
      setLoading(false);
    })();
  }, []);

  if (loading)
    return (
      <div className="py-12 text-center text-ops-muted">
        <Loader2 size={20} className="mx-auto animate-spin" />
        <p className="mt-2 text-xs">Aggregating deployments across the group…</p>
      </div>
    );
  if (!d || d.error)
    return <p className="py-12 text-center text-sm text-ops-muted">Couldn't load delivery metrics{d?.error ? `: ${d.error}` : ""}.</p>;

  const t = d.totals;
  const work = d.work_breakdown || {};
  const workTotal = Object.values(work).reduce((a, b) => a + b, 0) || 1;
  const maxDay = Math.max(1, ...d.per_day.map((x) => x.total));
  const envs = Object.keys(t.by_env || {});

  return (
    <div className="overflow-y-auto p-5">
      {/* top KPIs */}
      <div className="mb-5 grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
          <div className="text-2xl font-bold text-ops-text">{t.deployments}</div>
          <div className="text-[11px] uppercase tracking-wide text-ops-muted">Deploys / {d.window_days}d</div>
        </div>
        <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
          <div className="text-2xl font-bold text-emerald-400">{t.success_rate}%</div>
          <div className="text-[11px] uppercase tracking-wide text-ops-muted">Success rate</div>
        </div>
        <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
          <div className="text-2xl font-bold text-ops-accent">{t.today}</div>
          <div className="text-[11px] uppercase tracking-wide text-ops-muted">Deploys today</div>
        </div>
        <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
          <div className="text-2xl font-bold text-ops-text">{d.merged_mrs}</div>
          <div className="text-[11px] uppercase tracking-wide text-ops-muted">Merged MRs</div>
        </div>
      </div>

      {/* by environment */}
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">Deployments by environment</div>
      <div className="mb-5 flex flex-wrap gap-2">
        {envs.length === 0 && <p className="text-xs text-ops-muted">No deployments in window.</p>}
        {envs.map((e) => (
          <div key={e} className="flex items-center gap-1.5 rounded-lg border border-ops-border bg-ops-panel/50 px-2.5 py-1.5 text-xs">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: ENV_COLORS[e] || ENV_COLORS.OTHER }} />
            <span className="font-medium">{e}</span>
            <span className="text-ops-muted">{t.by_env[e]}</span>
          </div>
        ))}
      </div>

      {/* work breakdown (LLM-classified) */}
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
        Work shipped (AI-classified)
      </div>
      <div className="mb-1 flex h-2.5 w-full overflow-hidden rounded-full bg-ops-bg">
        {Object.entries(work).map(([k, v]) => (
          <div key={k} style={{ width: `${(100 * v) / workTotal}%`, background: WORK_COLORS[k] || WORK_COLORS.other }} title={`${k}: ${v}`} />
        ))}
      </div>
      <div className="mb-5 flex flex-wrap gap-3 text-[11px] text-ops-muted">
        {Object.keys(work).length === 0 && <span>classification pending…</span>}
        {Object.entries(work).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: WORK_COLORS[k] || WORK_COLORS.other }} />
            {k} <span className="text-ops-text">{v}</span>
          </span>
        ))}
      </div>

      {/* per-day */}
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">Deployments per day</div>
      <div className="mb-5 space-y-1.5">
        {d.per_day.map((row) => (
          <div key={row.date} className="flex items-center gap-2">
            <span className="w-16 shrink-0 text-[11px] text-ops-muted">{row.date.slice(5)}</span>
            <div className="flex-1">
              <div className="flex h-3 items-center" style={{ width: `${(100 * row.total) / maxDay}%`, minWidth: "2%" }}>
                <Bar data={row.by_env} total={row.total} />
              </div>
            </div>
            <span className="w-7 shrink-0 text-right text-[11px] font-medium text-ops-text">{row.total}</span>
          </div>
        ))}
      </div>

      {/* per project */}
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
        <Rocket size={12} /> Top projects by deployments
      </div>
      <div className="space-y-1.5">
        {d.per_project.slice(0, 25).map((p) => {
          const ptotal = Object.values(p.deploys).reduce((a, b) => a + b, 0);
          return (
            <div key={p.project} className="rounded-lg border border-ops-border bg-ops-panel/50 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium" title={p.project}>{p.project.replace(/^DOL\//, "")}</span>
                <span className="shrink-0 text-[11px] text-ops-muted">
                  {ptotal} deploys · {p.merged_mrs} MRs
                </span>
              </div>
              {ptotal > 0 && (
                <div className="mt-1.5 flex items-center gap-2">
                  <Bar data={p.deploys} total={ptotal} />
                  <span className="shrink-0 text-[10px] text-ops-muted">
                    {Object.entries(p.deploys).map(([e, n]) => `${e} ${n}`).join(" · ")}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
