import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  ExternalLink,
  FileDown,
  GitBranch,
  Loader2,
  RefreshCw,
  RotateCw,
  Sparkles,
  X,
} from "lucide-react";
import {
  analyze,
  fetchExport,
  fetchFailures,
  refreshFailures,
  type AnalyzeBody,
  type ExportReport,
  type FailuresReport,
} from "../lib/reports";
import { Markdown } from "./Markdown";
import { DeliveryPanel } from "./DeliveryPanel";
import { OverviewPanel } from "./OverviewPanel";
import { ReportDocument } from "./ReportDocument";
import { useAuth } from "../context/AuthContext";

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return `${Math.round(s)}s ago`;
  if (s < 5400) return `${Math.round(s / 60)}m ago`;
  if (s < 129600) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

interface Analysis {
  title: string;
  text: string;
  streaming: boolean;
}

export function ReportModal({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [report, setReport] = useState<FailuresReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [tab, setTab] = useState<"overview" | "delivery" | "failures" | "report">("overview");
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

  const load = async () => {
    setLoading(true);
    setReport(await fetchFailures());
    setLoading(false);
  };
  useEffect(() => {
    load();
  }, []);

  const doRefresh = async () => {
    setRefreshing(true);
    const r = await refreshFailures();
    if (r) setReport(r);
    setRefreshing(false);
  };

  const runAnalysis = async (title: string, body: AnalyzeBody) => {
    setAnalysis({ title, text: "", streaming: true });
    await analyze(body, (t) =>
      setAnalysis((a) => (a ? { ...a, text: a.text + t } : a)),
    );
    setAnalysis((a) => (a ? { ...a, streaming: false } : a));
  };

  const s = report?.summary;

  return (
    <>
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="glass flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-ops-border shadow-glow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center justify-between border-b border-ops-border px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gemini shadow-glow">
              <AlertTriangle size={18} className="text-white" />
            </span>
            <div>
              <h2 className="text-sm font-semibold leading-tight">Delivery &amp; Reliability</h2>
              <p className="text-[11px] text-ops-muted">
                {report
                  ? `group ${report.group} · ${report.gitlab.projects_scanned} projects · updated ${timeAgo(report.generated_at)}`
                  : "GitLab pipelines + Kubernetes pods"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && !analysis && (
              <button
                onClick={doRefresh}
                disabled={refreshing}
                className="flex items-center gap-1 rounded-lg border border-ops-border px-2.5 py-1.5 text-xs text-ops-text hover:border-ops-accent/50 disabled:opacity-50"
              >
                <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} /> Rescan
              </button>
            )}
            <button onClick={onClose} className="text-ops-muted hover:text-ops-text">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* analysis view */}
        {analysis ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <button
              onClick={() => setAnalysis(null)}
              className="flex items-center gap-1.5 px-5 py-3 text-xs text-ops-muted hover:text-ops-text"
            >
              <ArrowLeft size={14} /> Back to failures
            </button>
            <div className="overflow-y-auto px-5 pb-5">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Sparkles size={15} className="text-ops-accent" />
                {analysis.title}
              </div>
              {analysis.text ? (
                <Markdown content={analysis.text} />
              ) : (
                <div className="flex items-center gap-2 py-6 text-sm text-ops-muted">
                  <Loader2 size={15} className="animate-spin" /> Gathering logs and analyzing…
                </div>
              )}
              {analysis.streaming && analysis.text && (
                <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-ops-accent align-middle" />
              )}
            </div>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex gap-1 border-b border-ops-border px-5">
              {(["overview", "delivery", "failures", "report"] as const).map((tb) => (
                <button
                  key={tb}
                  onClick={() => setTab(tb)}
                  className={
                    "border-b-2 px-3 py-2 text-xs font-medium capitalize transition " +
                    (tab === tb
                      ? "border-ops-accent text-ops-text"
                      : "border-transparent text-ops-muted hover:text-ops-text")
                  }
                >
                  {tb}
                </button>
              ))}
            </div>
            {tab === "overview" ? (
              <OverviewPanel />
            ) : tab === "delivery" ? (
              <DeliveryPanel />
            ) : tab === "report" ? (
              <div className="p-6">
                <div className="mx-auto max-w-md rounded-xl border border-ops-border bg-ops-panel/50 p-5">
                  <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                    <FileDown size={15} className="text-ops-accent" /> Generate a report
                  </div>
                  <p className="mb-4 text-[11px] text-ops-muted">
                    Pick a date range, generate a professional report, then download it as PDF.
                  </p>
                  <div className="mb-3 grid grid-cols-2 gap-3">
                    <label className="text-[11px] text-ops-muted">
                      From
                      <input
                        type="date"
                        value={from}
                        max={to}
                        onChange={(e) => setFrom(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm text-ops-text outline-none focus:border-ops-accent"
                      />
                    </label>
                    <label className="text-[11px] text-ops-muted">
                      To
                      <input
                        type="date"
                        value={to}
                        min={from}
                        max={today}
                        onChange={(e) => setTo(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm text-ops-text outline-none focus:border-ops-accent"
                      />
                    </label>
                  </div>
                  <div className="mb-4 flex flex-wrap gap-1.5">
                    {([["7d", 7], ["14d", 14], ["30d", 30]] as const).map(([lbl, days]) => (
                      <button
                        key={lbl}
                        onClick={() => {
                          setTo(today);
                          setFrom(new Date(Date.now() - days * 86400000).toISOString().slice(0, 10));
                        }}
                        className="rounded-lg border border-ops-border px-2.5 py-1 text-[11px] text-ops-muted hover:border-ops-accent/50 hover:text-ops-text"
                      >
                        Last {lbl}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={generate}
                    disabled={generating}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-gemini px-3 py-2 text-sm font-medium text-white shadow-glow disabled:opacity-50"
                  >
                    {generating ? <Loader2 size={15} className="animate-spin" /> : <FileDown size={15} />}
                    {generating ? "Generating… (scanning GitLab + K8s)" : "Generate report"}
                  </button>
                </div>
              </div>
            ) : loading ? (
              <div className="py-12 text-center text-ops-muted">
                <Loader2 size={20} className="mx-auto animate-spin" />
                <p className="mt-2 text-xs">Scanning GitLab + Kubernetes…</p>
              </div>
        ) : !report ? (
          <p className="py-12 text-center text-sm text-ops-muted">Couldn't load the report.</p>
        ) : (
          <div className="overflow-y-auto p-5">
            {/* summary cards */}
            <div className="mb-5 grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
                <div className="text-2xl font-bold text-red-400">{s?.failed_pipelines ?? 0}</div>
                <div className="text-[11px] uppercase tracking-wide text-ops-muted">Failed pipelines</div>
              </div>
              <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
                <div className="text-2xl font-bold text-amber-400">{s?.failed_pods ?? 0}</div>
                <div className="text-[11px] uppercase tracking-wide text-ops-muted">Failing pods</div>
              </div>
              <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3 text-center">
                <div className="text-2xl font-bold text-ops-text">{s?.projects_scanned ?? 0}</div>
                <div className="text-[11px] uppercase tracking-wide text-ops-muted">Projects scanned</div>
              </div>
            </div>

            {/* failed pipelines */}
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
              <GitBranch size={13} /> Failed pipelines (last {report.window_hours}h)
            </div>
            {report.gitlab.error && (
              <p className="mb-2 text-[11px] text-red-300">GitLab: {report.gitlab.error}</p>
            )}
            <div className="space-y-2">
              {report.gitlab.failed_pipelines.length === 0 && (
                <p className="py-2 text-xs text-ops-muted">No failed pipelines. 🎉</p>
              )}
              {report.gitlab.failed_pipelines.slice(0, 40).map((p) => (
                <div key={`${p.project_id}-${p.pipeline_id}`} className="rounded-xl border border-ops-border bg-ops-panel/50 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium" title={p.project}>{p.project}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-ops-muted">
                        <span className="font-mono">#{p.pipeline_id}</span>
                        <span className="flex items-center gap-1"><GitBranch size={10} />{p.ref}</span>
                        <span>{timeAgo(p.created_at)}</span>
                        <a href={p.web_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5 text-ops-accent hover:underline">
                          open <ExternalLink size={10} />
                        </a>
                      </div>
                    </div>
                    <button
                      onClick={() => runAnalysis(`Pipeline #${p.pipeline_id} — ${p.project}`, { type: "pipeline", project_id: p.project_id, pipeline_id: p.pipeline_id })}
                      className="flex shrink-0 items-center gap-1 rounded-lg bg-gemini px-2.5 py-1.5 text-xs font-medium text-white shadow-glow"
                    >
                      <Sparkles size={12} /> Analyze
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* failing pods */}
            <div className="mb-3 mt-6 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ops-muted">
              <Boxes size={13} /> Failing Kubernetes pods
            </div>
            {report.kubernetes.error && (
              <p className="mb-2 text-[11px] text-red-300">Kubernetes: {report.kubernetes.error}</p>
            )}
            <div className="space-y-2">
              {report.kubernetes.failed_pods.length === 0 && (
                <p className="py-2 text-xs text-ops-muted">No failing pods. 🎉</p>
              )}
              {report.kubernetes.failed_pods.slice(0, 40).map((p) => (
                <div key={`${p.namespace}-${p.pod}`} className="rounded-xl border border-ops-border bg-ops-panel/50 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium" title={p.pod}>{p.pod}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-ops-muted">
                        <span className="rounded bg-ops-bg px-1.5 py-0.5">{p.namespace}</span>
                        <span className="text-red-300">{p.reason}</span>
                        <span>{p.restarts} restarts</span>
                      </div>
                    </div>
                    <button
                      onClick={() => runAnalysis(`Pod ${p.pod}`, { type: "pod", namespace: p.namespace, pod: p.pod })}
                      className="flex shrink-0 items-center gap-1 rounded-lg bg-gemini px-2.5 py-1.5 text-xs font-medium text-white shadow-glow"
                    >
                      <Sparkles size={12} /> Analyze
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-5 flex items-center justify-center gap-1 text-center text-[10px] text-ops-muted">
              <RotateCw size={10} /> Auto-refreshes in the background every few minutes.
            </p>
          </div>
            )}
          </div>
        )}
      </div>
    </div>
    {doc && <ReportDocument data={doc} onClose={() => setDoc(null)} />}
    </>
  );
}
