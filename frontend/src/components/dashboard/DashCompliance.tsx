import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ChevronDown, ChevronRight, Layers, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import {
  fetchCompliance,
  fetchComplianceAsset,
  fetchControlDetail,
  streamComplianceSummary,
  type AssetControls,
  type ComplianceAsset,
  type ComplianceOverview,
  type ControlDetail,
} from "../../lib/reports";
import { Markdown } from "../Markdown";
import { useDashColors } from "./DashTheme";
import { Card, Kpi } from "./ui";

const ENVS = ["dev", "sit", "demo", "local", "uat"];
type Filter = "failed" | "passed" | "all";

function scoreColor(pct: number): string {
  if (pct >= 90) return "#34d399";
  if (pct >= 75) return "#a3e635";
  if (pct >= 60) return "#facc15";
  if (pct >= 45) return "#fbbf24";
  if (pct >= 25) return "#fb923c";
  return "#f87171";
}
function assetLabel(a: { asset_id: string; asset_uuid: string; platform: string }): string {
  const id = a.asset_id || "";
  const uuidLike = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) || id === a.asset_uuid;
  return !id || uuidLike ? `${a.platform} · unnamed asset` : id;
}
function statusColor(status: string, C: ReturnType<typeof useDashColors>): string {
  const s = (status || "").toLowerCase();
  if (s === "failed") return "#f87171";
  if (s === "passed") return "#34d399";
  if (s.includes("not applicable")) return "#a3e635";
  return C.muted;
}

export function DashCompliance() {
  const C = useDashColors();
  const [env, setEnv] = useState("dev");
  const [o, setO] = useState<ComplianceOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Record<string, Filter>>({});
  const [drill, setDrill] = useState<Record<string, AssetControls | null>>({});
  const [ev, setEv] = useState<Record<string, ControlDetail | null>>({});
  const [openCtl, setOpenCtl] = useState<string | null>(null);
  const [brief, setBrief] = useState("");
  const [briefing, setBriefing] = useState(false);

  const loadDrill = async (uuid: string, f: Filter, cache: Record<string, AssetControls | null>) => {
    const key = `${uuid}|${f}`;
    if (key in cache) return;
    setDrill((d) => ({ ...d, [key]: null }));
    const res = await fetchComplianceAsset(uuid, env, f);
    setDrill((d) => ({ ...d, [key]: res }));
  };

  useEffect(() => {
    setLoading(true); setBrief(""); setSelected(null); setDrill({}); setEv({}); setOpenCtl(null);
    (async () => {
      const data = await fetchCompliance(env);
      setO(data); setLoading(false);
      if (data && data.assets.length) {
        setSelected(data.assets[0].asset_uuid);
        loadDrill(data.assets[0].asset_uuid, "failed", {});
      }
    })();
  }, [env]);

  const select = async (a: ComplianceAsset) => {
    setSelected(a.asset_uuid); setOpenCtl(null);
    await loadDrill(a.asset_uuid, filter[a.asset_uuid] || "failed", drill);
  };
  const setAssetFilter = async (uuid: string, f: Filter) => {
    setFilter((x) => ({ ...x, [uuid]: f })); setOpenCtl(null);
    await loadDrill(uuid, f, drill);
  };
  const toggleControl = async (uuid: string, controlId: string) => {
    const k = `${uuid}|${controlId}`;
    if (openCtl === k) { setOpenCtl(null); return; }
    setOpenCtl(k);
    if (!(k in ev)) {
      setEv((e) => ({ ...e, [k]: null }));
      const detail = await fetchControlDetail(uuid, controlId, env);
      setEv((e) => ({ ...e, [k]: detail }));
    }
  };
  const genBrief = async () => { setBrief(""); setBriefing(true); await streamComplianceSummary(env, (t) => setBrief((p) => p + t)); setBriefing(false); };

  const envBar = (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[12px]" style={{ color: C.muted }}>Environment:</span>
      {ENVS.map((e) => (
        <button key={e} onClick={() => setEnv(e)} className="rounded-lg px-2.5 py-1 text-[12px] font-medium uppercase"
          style={e === env ? { background: C.accent, color: "#fff" } : { border: `1px solid ${C.border}`, color: C.muted }}>{e}</button>
      ))}
    </div>
  );

  if (loading) return <div className="space-y-4">{envBar}<div className="py-16 text-center" style={{ color: C.muted }}><Loader2 size={22} className="mx-auto animate-spin" /><p className="mt-2 text-sm">Scanning compliance posture for {env}…</p></div></div>;
  if (!o || o.error) return <div className="space-y-4">{envBar}<Card><p className="py-8 text-center text-sm" style={{ color: C.muted }}>{o?.error || "Couldn't load compliance data."}</p></Card></div>;

  const f = o.fleet;
  const platData = o.by_platform.map((p) => ({ name: p.platform, pct: p.compliance_pct, failed: p.failed, assets: p.assets }));
  const sel = selected ? o.assets.find((a) => a.asset_uuid === selected) : null;
  const topFail = o.top_failing_controls || [];

  return (
    <div className="space-y-5">
      {envBar}

      <div className="flex flex-wrap items-center gap-2.5 rounded-2xl px-4 py-3 text-sm font-medium"
        style={{ background: C.dark ? "#171a2b" : "#f8fafc", color: scoreColor(f.compliance_pct), border: `1px solid ${scoreColor(f.compliance_pct)}55` }}>
        <ShieldCheck size={18} />
        <span style={{ color: C.text }}>Overall compliance for <b>{o.env}</b>:&nbsp;</span>
        <b>{f.compliance_pct}%</b>
        <span style={{ color: C.muted }}>· {(f.failed || 0).toLocaleString()} failed controls · {f.assets} assets scanned</span>
        <span className="ml-auto text-[12px] font-normal" style={{ color: C.muted }}>{o.ssp_count} SSPs</span>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi value={`${f.compliance_pct}%`} label="Overall compliance" tone={scoreColor(f.compliance_pct)} />
        <Kpi value={f.assets} label="Assets scanned" />
        <Kpi value={(f.failed || 0).toLocaleString()} label="Failed controls" tone="#f87171" />
        <Kpi value={o.ssp_count} label="SSPs published" tone={C.accent} />
      </div>

      <Card title="Assets by compliance band">
        <div className="grid grid-cols-3 gap-3">
          {([["≥90% compliant", o.bands.good, "#34d399"], ["70–90%", o.bands.warn, "#facc15"], ["<70% at risk", o.bands.poor, "#f87171"]] as const).map(([label, n, col]) => (
            <div key={label} className="rounded-xl p-3 text-center" style={{ background: C.bg, border: `1px solid ${col}33` }}>
              <div className="text-[24px] font-bold" style={{ color: col }}>{n}</div>
              <div className="text-[11px]" style={{ color: C.muted }}>{label}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Compliance by platform">
          {platData.length === 0 ? <p className="text-sm" style={{ color: C.muted }}>No scanned assets in {env}.</p> : (
            <ResponsiveContainer width="100%" height={Math.max(120, platData.length * 34)}>
              <BarChart data={platData} layout="vertical" margin={{ left: 10, right: 44 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fill: C.muted, fontSize: 11 }} unit="%" />
                <YAxis type="category" dataKey="name" width={100} tick={{ fill: C.text, fontSize: 11 }} />
                <Tooltip cursor={{ fill: C.dark ? "#ffffff0f" : "#0000000a" }} contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8 }} itemStyle={{ color: C.text }} labelStyle={{ color: C.muted }}
                  formatter={(v: number, _n, p) => [`${v}% · ${(p.payload as { failed: number; assets: number }).failed} failed · ${(p.payload as { assets: number }).assets} assets`, "Compliance"]} />
                <Bar dataKey="pct" radius={[0, 5, 5, 0]} label={{ position: "right", fill: C.muted, fontSize: 11, formatter: (v: number) => `${v}%` }}>
                  {platData.map((d, i) => <Cell key={i} fill={scoreColor(d.pct)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide" style={{ color: "#f87171" }}>
            <AlertTriangle size={14} /> Top failing controls (systemic)
          </div>
          <p className="mb-2 text-[11px]" style={{ color: C.muted }}>Controls failing on the most assets — fixing these has the widest impact.</p>
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {topFail.length === 0 && <p className="text-sm" style={{ color: C.muted }}>Nothing failing 🎉</p>}
            {topFail.map((c) => (
              <div key={c.control_id} className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px]" style={{ background: C.bg }}>
                <span className="shrink-0 font-mono text-[11px]" style={{ color: "#f87171" }}>{c.control_id}</span>
                <span className="min-w-0 flex-1 truncate" style={{ color: C.text }} title={c.title}>{c.title || c.platform}</span>
                <span className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{ background: "#f8717122", color: "#f87171" }}>{c.assets_failing} assets</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Master-detail asset explorer */}
      <Card>
        <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide" style={{ color: C.muted }}>
          <Layers size={13} /> Asset explorer — {o.asset_count} scanned{o.skipped_no_data ? ` · ${o.skipped_no_data} skipped (empty scans)` : ""}
        </div>
        <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
          {/* left: list */}
          <div className="max-h-[540px] space-y-1 overflow-y-auto pr-1">
            {o.assets.map((a) => {
              const on = selected === a.asset_uuid;
              return (
                <button key={a.asset_uuid} onClick={() => select(a)} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left transition"
                  style={{ background: on ? C.accent + "18" : C.bg, border: `1px solid ${on ? C.accent : "transparent"}` }}>
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: scoreColor(a.compliance_pct) }} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] font-medium" style={{ color: C.text }} title={`${a.asset_id} · ${a.asset_uuid}`}>{assetLabel(a)}</div>
                    <div className="flex items-center gap-1.5 text-[10px]" style={{ color: C.muted }}><span>{a.platform}</span><span>·</span><span className="font-mono">#{a.asset_uuid.slice(-6)}</span></div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-[13px] font-semibold" style={{ color: scoreColor(a.compliance_pct) }}>{a.compliance_pct}%</div>
                    <div className="text-[10px]" style={{ color: "#f87171" }}>{a.failed} ✗</div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* right: detail */}
          <div className="rounded-xl p-3" style={{ background: C.bg, border: `1px solid ${C.border}` }}>
            {!sel ? (
              <div className="flex h-full items-center justify-center py-16 text-sm" style={{ color: C.muted }}>Select an asset to inspect its controls.</div>
            ) : (
              <AssetDetail asset={sel} C={C} af={filter[sel.asset_uuid] || "failed"}
                data={drill[`${sel.asset_uuid}|${filter[sel.asset_uuid] || "failed"}`]}
                setFilter={(k) => setAssetFilter(sel.asset_uuid, k)}
                ev={ev} openCtl={openCtl} onControl={(cid) => toggleControl(sel.asset_uuid, cid)} />
            )}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title={`Published SSPs (${o.ssp_count})`}>
          <div className="max-h-72 space-y-1.5 overflow-y-auto">
            {o.ssps.map((s, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12px]" style={{ background: C.bg }}>
                <span className="min-w-0 flex-1 truncate" style={{ color: C.text }} title={s.ssp_name}>{s.ssp_name}</span>
                <span style={{ color: C.muted }}>{(s.platforms || []).join(", ")}</span>
                <span className="font-semibold" style={{ color: C.accent }}>{s.total_controls} ctrl</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wide" style={{ color: C.accent }}><Sparkles size={14} /> AI compliance brief</div>
            <button onClick={genBrief} disabled={briefing} className="rounded-lg px-2.5 py-1 text-[12px] font-medium text-white disabled:opacity-50" style={{ background: C.accent }}>{briefing ? "Writing…" : brief ? "Regenerate" : "Generate"}</button>
          </div>
          {brief ? <div className="dash-analysis text-[13px]"><Markdown content={brief} /></div>
            : briefing ? <div className="flex items-center gap-2 py-3 text-sm" style={{ color: C.muted }}><Loader2 size={14} className="animate-spin" /> Analyzing posture…</div>
            : <p className="text-[12px]" style={{ color: C.muted }}>Generate an AI compliance-officer brief: posture, weakest platforms/assets, systemic risks, and prioritized remediation — ready for the CISO or an auditor.</p>}
        </Card>
      </div>
    </div>
  );
}

function AssetDetail({ asset, C, af, data, setFilter, ev, openCtl, onControl }: {
  asset: ComplianceAsset; C: ReturnType<typeof useDashColors>; af: Filter;
  data: AssetControls | null | undefined; setFilter: (f: Filter) => void;
  ev: Record<string, ControlDetail | null>; openCtl: string | null; onControl: (cid: string) => void;
}) {
  const donut = [
    { name: "Passed", value: asset.passed, color: "#34d399" },
    { name: "Failed", value: asset.failed, color: "#f87171" },
    { name: "N/A", value: asset.not_applicable, color: "#a3e635" },
    { name: "Not run", value: asset.not_run, color: "#94a3b8" },
  ].filter((d) => d.value > 0);
  return (
    <div>
      <div className="mb-2 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-semibold" style={{ color: C.text }} title={asset.asset_id}>{assetLabel(asset)}</div>
          <div className="text-[11px]" style={{ color: C.muted }}>{asset.platform} · {asset.catalog}</div>
          <div className="text-[10px]" style={{ color: C.muted }}>uuid {asset.asset_uuid} · last scan {asset.last_scan?.slice(0, 10)}</div>
        </div>
        <div className="text-right">
          <div className="text-[22px] font-bold leading-none" style={{ color: scoreColor(asset.compliance_pct) }}>{asset.compliance_pct}%</div>
          <div className="text-[10px]" style={{ color: C.muted }}>compliant</div>
        </div>
      </div>

      <div className="mb-2 flex items-center gap-3">
        <div style={{ width: 96, height: 96 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={donut} dataKey="value" innerRadius={30} outerRadius={46} paddingAngle={2} stroke="none">
                {donut.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip contentStyle={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8 }} itemStyle={{ color: C.text }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-1.5 text-[11px]">
          {donut.map((d) => (
            <div key={d.name} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: d.color }} /><span style={{ color: C.muted }}>{d.name}</span><span className="ml-auto font-semibold" style={{ color: C.text }}>{d.value}</span></div>
          ))}
        </div>
      </div>

      <div className="mb-2 flex items-center gap-1.5">
        {(["failed", "passed", "all"] as Filter[]).map((k) => (
          <button key={k} onClick={() => setFilter(k)} className="rounded-md px-2 py-0.5 text-[11px] font-medium capitalize"
            style={af === k ? { background: C.accent, color: "#fff" } : { border: `1px solid ${C.border}`, color: C.muted }}>{k}</button>
        ))}
      </div>

      <div className="max-h-[300px] space-y-0.5 overflow-y-auto">
        {data === undefined || data === null ? (
          <div className="flex items-center gap-2 py-3 text-[12px]" style={{ color: C.muted }}><Loader2 size={13} className="animate-spin" /> Loading controls…</div>
        ) : data.error ? (
          <p className="text-[12px]" style={{ color: "#f87171" }}>{data.error}</p>
        ) : data.controls.length === 0 ? (
          <p className="py-2 text-[12px]" style={{ color: C.muted }}>No {af === "all" ? "" : af} controls.</p>
        ) : (
          data.controls.slice(0, 200).map((c) => {
            const k = `${asset.asset_uuid}|${c.control_id}`;
            const detail = ev[k];
            const cOpen = openCtl === k;
            return (
              <div key={c.control_id}>
                <button onClick={() => onControl(c.control_id)} className="flex w-full items-start gap-2 rounded px-1.5 py-1 text-left text-[12px] hover:opacity-80">
                  {cOpen ? <ChevronDown size={12} className="mt-0.5 shrink-0" style={{ color: C.muted }} /> : <ChevronRight size={12} className="mt-0.5 shrink-0" style={{ color: C.muted }} />}
                  <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: statusColor(c.status, C) }} />
                  <span className="shrink-0 font-mono text-[11px]" style={{ color: statusColor(c.status, C) }}>{c.control_id}</span>
                  {c.title && <span className="min-w-0 flex-1" style={{ color: C.text }}>{c.title}</span>}
                </button>
                {cOpen && (
                  <div className="ml-6 mb-1 rounded-lg p-2 text-[11px]" style={{ background: C.card, border: `1px solid ${C.border}` }}>
                    {detail === undefined || detail === null ? (
                      <span className="flex items-center gap-1.5" style={{ color: C.muted }}><Loader2 size={11} className="animate-spin" /> Loading evidence…</span>
                    ) : detail.error ? <span style={{ color: "#f87171" }}>{detail.error}</span> : (
                      <div className="space-y-1.5">
                        <div><span style={{ color: C.muted }}>Status: </span><span style={{ color: statusColor(detail.status || "", C) }}>{detail.status}</span></div>
                        {detail.command_executed && <div><div style={{ color: C.muted }}>Command:</div><pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap rounded p-1.5 font-mono text-[10.5px]" style={{ background: C.bg, color: C.text }}>{detail.command_executed}</pre></div>}
                        <div><div style={{ color: C.muted }}>Evidence:</div><pre className="mt-0.5 max-h-56 overflow-auto whitespace-pre-wrap rounded p-1.5 font-mono text-[10.5px]" style={{ background: C.bg, color: C.text }}>{detail.evidence || "(none)"}</pre></div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
