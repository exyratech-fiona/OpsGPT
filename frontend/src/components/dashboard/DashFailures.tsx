import { useEffect, useState } from "react";
import { ArrowLeft, Boxes, ExternalLink, GitBranch, Loader2, RefreshCw, Sparkles } from "lucide-react";
import {
  analyze,
  fetchExport,
  fetchFailures,
  refreshFailures,
  type AnalyzeBody,
  type FailedPipeline,
  type FailedPod,
} from "../../lib/reports";
import type { DateRange } from "./Dashboard";
import { Markdown } from "../Markdown";
import { useAuth } from "../../context/AuthContext";
import { useDashColors } from "./DashTheme";
import { Card, Kpi } from "./ui";

interface Analysis { title: string; text: string; streaming: boolean }
interface View { pipelines: FailedPipeline[]; pods: FailedPod[]; label: string; projects: number; pipeErr?: string; podErr?: string; podsLive: boolean }

export function DashFailures({ range }: { range: DateRange }) {
  const C = useDashColors();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [v, setV] = useState<View | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

  const load = async () => {
    setLoading(true);
    if (range) {
      const ex = await fetchExport(range.from, range.to);
      setV(ex ? { pipelines: ex.failed_pipelines, pods: ex.failing_pods, label: `${range.from} → ${range.to}`, projects: 0, podsLive: true } : null);
    } else {
      const r = await fetchFailures();
      setV(r ? { pipelines: r.gitlab.failed_pipelines, pods: r.kubernetes.failed_pods, label: `last ${r.window_hours}h`, projects: r.summary.projects_scanned, pipeErr: r.gitlab.error, podErr: r.kubernetes.error, podsLive: false } : null);
    }
    setLoading(false);
  };
  useEffect(() => { load(); }, [range]);

  const rescan = async () => {
    setRefreshing(true);
    const res = await refreshFailures();
    if (res) setV({ pipelines: res.gitlab.failed_pipelines, pods: res.kubernetes.failed_pods, label: `last ${res.window_hours}h`, projects: res.summary.projects_scanned, pipeErr: res.gitlab.error, podErr: res.kubernetes.error, podsLive: false });
    setRefreshing(false);
  };

  const runAnalysis = async (title: string, body: AnalyzeBody) => {
    setAnalysis({ title, text: "", streaming: true });
    await analyze(body, (t) => setAnalysis((a) => (a ? { ...a, text: a.text + t } : a)));
    setAnalysis((a) => (a ? { ...a, streaming: false } : a));
  };

  if (loading)
    return (
      <div className="py-20 text-center" style={{ color: C.muted }}>
        <Loader2 size={22} className="mx-auto animate-spin" />
        <p className="mt-2 text-sm">{range ? "Scanning the selected date range…" : "Scanning GitLab + Kubernetes…"}</p>
      </div>
    );
  if (!v) return <p className="py-20 text-center text-sm" style={{ color: C.muted }}>Couldn't load failures.</p>;

  if (analysis)
    return (
      <Card>
        <button onClick={() => setAnalysis(null)} className="mb-3 flex items-center gap-1.5 text-[13px]" style={{ color: C.muted }}>
          <ArrowLeft size={15} /> Back to failures
        </button>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold" style={{ color: C.text }}>
          <Sparkles size={15} style={{ color: C.accent }} /> {analysis.title}
        </div>
        {analysis.text ? (
          <div className="dash-analysis text-[13.5px]"><Markdown content={analysis.text} /></div>
        ) : (
          <div className="flex items-center gap-2 py-6 text-sm" style={{ color: C.muted }}>
            <Loader2 size={15} className="animate-spin" /> Reading the real logs and analyzing…
          </div>
        )}
        {analysis.streaming && analysis.text && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse" style={{ background: C.accent }} />}
      </Card>
    );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="grid flex-1 grid-cols-3 gap-4">
          <Kpi value={v.pipelines.length} label="Failed pipelines" tone={v.pipelines.length ? C.danger : C.text} />
          <Kpi value={v.pods.length} label="Failing pods (now)" tone={v.pods.length ? C.warn : C.text} />
          <Kpi value={range ? "—" : v.projects} label="Projects scanned" />
        </div>
        {isAdmin && !range && (
          <button onClick={rescan} disabled={refreshing} className="ml-4 flex items-center gap-1.5 rounded-xl px-3 py-2 text-[13px]" style={{ border: `1px solid ${C.border}`, color: C.text }}>
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} /> Rescan
          </button>
        )}
      </div>

      <Card title={`Failed pipelines (${v.label})`}>
        {v.pipeErr && <p className="mb-2 text-[12px]" style={{ color: C.danger }}>GitLab: {v.pipeErr}</p>}
        <div className="space-y-2">
          {v.pipelines.length === 0 && <p className="text-sm" style={{ color: C.muted }}>No failed pipelines. 🎉</p>}
          {v.pipelines.slice(0, 60).map((p) => (
            <div key={`${p.project_id}-${p.pipeline_id}`} className="flex items-center justify-between gap-2 rounded-xl px-3 py-2" style={{ background: C.bg }}>
              <div className="min-w-0">
                <div className="truncate text-[13px] font-medium" style={{ color: C.text }} title={p.project}>{p.project.replace(/^DOL\//, "")}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px]" style={{ color: C.muted }}>
                  <span>#{p.pipeline_id}</span>
                  <span className="flex items-center gap-1"><GitBranch size={10} />{p.ref}</span>
                  {p.user && <span style={{ color: C.text }}>by {p.user}</span>}
                  <a href={p.web_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5" style={{ color: C.accent }}>open <ExternalLink size={10} /></a>
                </div>
              </div>
              <button onClick={() => runAnalysis(`Pipeline #${p.pipeline_id} — ${p.project}`, { type: "pipeline", project_id: p.project_id, pipeline_id: p.pipeline_id })}
                className="flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-white" style={{ background: C.accent }}>
                <Sparkles size={12} /> Why it failed
              </button>
            </div>
          ))}
        </div>
      </Card>

      <Card title={`Failing Kubernetes pods${range ? " (current — pods are real-time, not historical)" : ""}`}>
        {v.podErr && <p className="mb-2 text-[12px]" style={{ color: C.danger }}>Kubernetes: {v.podErr}</p>}
        <div className="space-y-2">
          {v.pods.length === 0 && <p className="text-sm" style={{ color: C.muted }}>No failing pods. 🎉</p>}
          {v.pods.slice(0, 60).map((p) => (
            <div key={`${p.namespace}-${p.pod}`} className="flex items-center justify-between gap-2 rounded-xl px-3 py-2" style={{ background: C.bg }}>
              <div className="min-w-0">
                <div className="truncate text-[13px] font-medium" style={{ color: C.text }} title={p.pod}>{p.pod}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px]" style={{ color: C.muted }}>
                  <span className="rounded px-1.5 py-0.5" style={{ background: C.card }}>{p.namespace}</span>
                  <span style={{ color: C.danger }}>{p.reason}</span>
                  <span>{p.restarts.toLocaleString()} restarts</span>
                </div>
              </div>
              <button onClick={() => runAnalysis(`Pod ${p.pod}`, { type: "pod", namespace: p.namespace, pod: p.pod })}
                className="flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium text-white" style={{ background: C.accent }}>
                <Sparkles size={12} /> Why it failed
              </button>
            </div>
          ))}
        </div>
      </Card>
      <div className="flex items-center justify-center gap-1 text-center text-[11px]" style={{ color: C.muted }}>
        <Boxes size={11} /> {range ? "Pipelines filtered to the selected dates. Click “Why it failed” for an AI root-cause from the real logs." : "Live view, auto-refreshed every few minutes."}
      </div>
    </div>
  );
}
