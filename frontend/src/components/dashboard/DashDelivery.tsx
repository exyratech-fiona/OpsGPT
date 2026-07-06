import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { fetchDelivery, fetchExport, type DeliveryReport } from "../../lib/reports";
import type { DateRange } from "./Dashboard";
import { ENV_C, ENV_ORDER } from "./theme";
import { useDashColors } from "./DashTheme";
import { Card, Kpi } from "./ui";
import { CustomerCard } from "./CustomerCard";
import { ReleaseReadiness } from "./ReleaseReadiness";
import { DayTrend, EnvBar, PeopleBar, WorkPie } from "./Charts";

export function DashDelivery({ range }: { range: DateRange }) {
  const C = useDashColors();
  const [d, setD] = useState<DeliveryReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const r = range ? (await fetchExport(range.from, range.to))?.delivery ?? null : await fetchDelivery();
      if (alive) { setD(r); setLoading(false); }
    })();
    return () => { alive = false; };
  }, [range]);

  if (loading)
    return (
      <div className="py-20 text-center" style={{ color: C.muted }}>
        <Loader2 size={22} className="mx-auto animate-spin" />
        <p className="mt-2 text-sm">{range ? "Scanning the selected date range…" : "Aggregating deployments across the group…"}</p>
      </div>
    );
  if (!d || d.error) return <p className="py-20 text-center text-sm" style={{ color: C.muted }}>Couldn't load delivery metrics{d?.error ? `: ${d.error}` : ""}.</p>;

  const t = d.totals;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi value={t.real_changes} label="Changes to real envs" tone={C.ok} />
        <Kpi value={`${t.success_rate}%`} label="Deploy success" tone={C.ok} />
        <Kpi value={`${t.change_failure_rate}%`} label="Change failure rate" tone={t.change_failure_rate > 20 ? C.danger : C.warn} />
        <Kpi value={t.prod_changes} label="Changes to PROD" tone={C.accent} />
      </div>

      <Card title="Promotion funnel — distinct changes reaching each environment">
        <EnvBar by_env={d.funnel} />
        <p className="mt-1 text-[11px]" style={{ color: C.muted }}>
          How many distinct changes reached each environment. DEV is auto-deploy on push; SIT→DEMO→UAT→PROD are manual promotions (manager-approved).
        </p>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Deployment volume by environment"><EnvBar by_env={t.by_env} /></Card>
        <Card title="Work shipped (AI-classified)"><WorkPie work={d.work_breakdown} /></Card>
      </div>

      <CustomerCard customers={d.per_customer} />

      <ReleaseReadiness backlog={d.release_backlog} />

      <Card title="Deployments per day"><DayTrend per_day={d.per_day} /></Card>

      <Card title="Whose changes reached real environments (SIT / DEMO / UAT / PROD)">
        <PeopleBar people={d.top_deployers} />
        <div className="mt-3 max-h-[26rem] overflow-y-auto">
          <div className="flex items-center gap-2 pb-1 text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>
            <span className="w-6" />
            <span className="flex-1">Developer</span>
            <span className="w-16 text-right">Real envs</span>
            <span className="w-12 text-right">DEV</span>
          </div>
          {d.top_deployers.map((p, i) => {
            const expanded = open === p.user;
            return (
              <div key={p.user} style={{ borderTop: `1px solid ${C.border}` }}>
                <button onClick={() => setOpen(expanded ? null : p.user)} className="flex w-full items-center gap-2 py-1.5 text-left text-[12.5px]">
                  {p.real > 0 ? (expanded ? <ChevronDown size={13} style={{ color: C.muted }} /> : <ChevronRight size={13} style={{ color: C.muted }} />) : <span className="w-[13px]" />}
                  <span className="w-4 text-right" style={{ color: C.muted }}>{i + 1}</span>
                  <span className="flex-1 truncate" style={{ color: C.text }}>{p.user}</span>
                  <span className="w-16 text-right font-semibold" style={{ color: p.real ? C.ok : C.muted }}>{p.real}</span>
                  <span className="w-12 text-right" style={{ color: C.muted }}>{p.dev}</span>
                </button>
                {expanded && (
                  <div className="mb-2 ml-7 rounded-lg p-2" style={{ background: C.bg }}>
                    {p.promotions.length === 0 && <p className="text-[11px]" style={{ color: C.muted }}>No real-env promotions in range.</p>}
                    {p.promotions.map((pr, j) => (
                      <div key={j} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1 text-[11.5px]" style={{ color: C.text }}>
                        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: (ENV_C[pr.env] || ENV_C.OTHER) + "22", color: ENV_C[pr.env] || ENV_C.OTHER }}>{pr.env}</span>
                        <span className="font-medium">{pr.project.replace(/^DOL\//, "")}</span>
                        <span style={{ color: C.muted }}>· {pr.ref}</span>
                        {pr.title && <span style={{ color: C.muted }}>· {pr.title}</span>}
                        <span style={{ color: C.muted }}>· {pr.date}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          {d.top_deployers.length === 0 && <p className="text-sm" style={{ color: C.muted }}>No attributed deployments.</p>}
        </div>
        <p className="mt-2 text-[11px]" style={{ color: C.muted }}>
          {d.top_deployers.length} contributors · ranked by <b>whose commits were promoted to real envs</b>. SIT/DEMO/UAT/PROD are manual (manager-approved); the count is the developer whose code was promoted, not who clicked deploy. DEV (auto on push) is shown separately. <b>Click a row</b> to see exactly which changes.
        </p>
      </Card>

      <Card title="Per-project deployments">
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr style={{ color: C.muted }}>
                <th className="px-2 py-1.5 text-left font-medium">Project</th>
                <th className="px-2 py-1.5 text-right font-medium">Deploys</th>
                <th className="px-2 py-1.5 text-left font-medium">By environment</th>
                <th className="px-2 py-1.5 text-right font-medium">MRs</th>
              </tr>
            </thead>
            <tbody>
              {d.per_project.slice(0, 30).map((p) => {
                const tot = Object.values(p.deploys).reduce((a, b) => a + b, 0);
                return (
                  <tr key={p.project} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td className="px-2 py-1.5" style={{ color: C.text }}>{p.project.replace(/^DOL\//, "")}</td>
                    <td className="px-2 py-1.5 text-right font-semibold" style={{ color: C.text }}>{tot}</td>
                    <td className="px-2 py-1.5">
                      <div className="flex flex-wrap gap-1">
                        {ENV_ORDER.filter((e) => p.deploys[e]).map((e) => (
                          <span key={e} className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: ENV_C[e] + "22", color: ENV_C[e] }}>{e} {p.deploys[e]}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-right" style={{ color: C.muted }}>{p.merged_mrs}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
