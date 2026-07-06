import { authedFetch } from "./auth";

export interface FailedPipeline {
  project_id: number;
  project: string;
  pipeline_id: number;
  ref: string;
  sha: string;
  web_url: string;
  created_at: string;
  user?: string;
}

export interface ReleaseBacklog {
  project: string;
  project_id: number | null;
  customer: string;
  pending: number;
  reached: string[];
}

export interface Customer {
  customer: string;
  deploys: number;
  real: number;
  dev: number;
  by_env: Record<string, number>;
  failed: number;
  mrs: number;
  projects: number;
  failed_pipelines?: number;
}

export interface Promotion {
  project: string;
  env: string;
  ref: string;
  sha: string;
  date: string;
  title: string;
}

export interface Deployer {
  user: string;
  total: number;
  dev: number;
  real: number;
  by_env: Record<string, number>;
  promotions: Promotion[];
}

export interface FailedPod {
  namespace: string;
  pod: string;
  reason: string;
  restarts: number;
  phase: string;
  started_at: string | null;
}

export interface FailuresReport {
  generated_at: string;
  window_hours: number;
  group: string;
  gitlab: { projects_scanned: number; failed_pipelines: FailedPipeline[]; error?: string };
  kubernetes: { failed_pods: FailedPod[]; error?: string };
  summary: { failed_pipelines: number; projects_scanned: number; failed_pods: number };
}

export async function fetchFailures(): Promise<FailuresReport | null> {
  const r = await authedFetch("/reports/failures");
  if (!r.ok) return null;
  return (await r.json()) as FailuresReport;
}

export interface Alert {
  id: string;
  kind: "pipeline" | "pod";
  title: string;
  project?: string;
  project_id?: number;
  pipeline_id?: number;
  ref?: string;
  namespace?: string;
  pod?: string;
  reason?: string;
  restarts?: number;
  web_url?: string | null;
  created_at?: string | null;
  detected_at: string;
  analysis: string;
  acked: boolean;
}

export interface AlertFeed {
  alerts: Alert[];
  unread: number;
  count: number;
}

export async function fetchAlerts(): Promise<AlertFeed | null> {
  const r = await authedFetch("/reports/alerts");
  if (!r.ok) return null;
  return (await r.json()) as AlertFeed;
}

export async function ackAlert(id: string | null): Promise<AlertFeed | null> {
  const r = await authedFetch("/reports/alerts/ack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (!r.ok) return null;
  return (await r.json()) as AlertFeed;
}

export async function clearAlerts(): Promise<AlertFeed | null> {
  const r = await authedFetch("/reports/alerts/clear", { method: "POST" });
  if (!r.ok) return null;
  return (await r.json()) as AlertFeed;
}

export async function scanAlerts(): Promise<{ new: number; alerts: Alert[] } | null> {
  const r = await authedFetch("/reports/alerts/scan", { method: "POST" });
  if (!r.ok) return null;
  return (await r.json()) as { new: number; alerts: Alert[] };
}

export interface DeliveryProject {
  project: string;
  deploys: Record<string, number>;
  success: number;
  failed: number;
  last_deploy: string | null;
  merged_mrs: number;
}

export interface DeliveryReport {
  generated_at: string;
  window_days: number;
  group: string;
  totals: {
    deployments: number;
    failed_deployments: number;
    success_rate: number;
    change_failure_rate: number;
    real_changes: number;
    prod_changes: number;
    lead_time_hours: number | null;
    mttr_hours: number | null;
    by_env: Record<string, number>;
    today: number;
  };
  work_breakdown: Record<string, number>;
  merged_mrs: number;
  per_day: { date: string; by_env: Record<string, number>; total: number }[];
  per_project: DeliveryProject[];
  per_customer: Customer[];
  release_backlog: ReleaseBacklog[];
  top_deployers: Deployer[];
  funnel: Record<string, number>;
  error?: string;
}

export async function fetchDelivery(): Promise<DeliveryReport | null> {
  const r = await authedFetch("/reports/delivery");
  if (!r.ok) return null;
  return (await r.json()) as DeliveryReport;
}

export interface OverviewReport {
  generated_at: string;
  group: string;
  window_days: number;
  headline: {
    deploys_window: number;
    deploys_today: number;
    success_rate: number;
    change_failure_rate: number;
    real_changes: number;
    prod_changes: number;
    lead_time_hours: number | null;
    mttr_hours: number | null;
    features: number;
    bugfixes: number;
    failing_pods: number;
    failed_pipelines: number;
    projects_scanned: number;
  };
  by_env: Record<string, number>;
  funnel: Record<string, number>;
  work_breakdown: Record<string, number>;
  per_day: { date: string; by_env: Record<string, number>; total: number }[];
  products: { product: string; deploys: number; mrs: number; by_env: Record<string, number> }[];
  per_customer: Customer[];
  top_deployers: Deployer[];
  attention: {
    pods: { namespace: string; pod: string; reason: string; restarts: number }[];
    pipelines: { project: string; count: number }[];
  };
}

export async function fetchOverview(): Promise<OverviewReport | null> {
  const r = await authedFetch("/reports/overview");
  if (!r.ok) return null;
  return (await r.json()) as OverviewReport;
}

export interface ExportReport {
  generated_at: string;
  group: string;
  from: string;
  to: string;
  delivery: DeliveryReport;
  failed_pipelines: FailedPipeline[];
  failing_pods: FailedPod[];
  error?: string;
}

export async function fetchExport(from: string, to: string): Promise<ExportReport | null> {
  const r = await authedFetch(`/reports/export?from=${from}&to=${to}`);
  if (!r.ok) return null;
  return (await r.json()) as ExportReport;
}

async function readTokenStream(res: Response, onToken: (t: string) => void): Promise<void> {
  if (!res.ok || !res.body) {
    onToken(`\n_Failed (HTTP ${res.status})._`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const evt = JSON.parse(line.slice(5).trim());
        if (evt.type === "token") onToken(evt.content as string);
        else if (evt.type === "error") onToken(`\n_${evt.message}_`);
      } catch {
        /* partial */
      }
    }
  }
}

export async function releaseNotes(project_id: number, days: number, onToken: (t: string) => void): Promise<void> {
  const res = await authedFetch("/reports/release-notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id, days }),
  });
  await readTokenStream(res, onToken);
}

export async function streamDigest(onToken: (t: string) => void): Promise<void> {
  const res = await authedFetch("/reports/digest", { method: "POST" });
  await readTokenStream(res, onToken);
}

export async function sendDigest(): Promise<{ ok: boolean; message: string } | null> {
  const r = await authedFetch("/reports/digest/send", { method: "POST" });
  if (!r.ok) return null;
  return (await r.json()) as { ok: boolean; message: string };
}

// ---- GRC compliance ----
export interface CompliancePlatform {
  platform: string; assets: number; controls: number; passed: number;
  failed: number; not_applicable: number; compliance_pct: number;
}
export interface ComplianceAsset {
  asset_id: string; asset_uuid: string; platform: string; catalog?: string;
  last_scan?: string; controls: number; passed: number; failed: number;
  not_applicable: number; not_run: number; compliance_pct: number;
}
export interface ComplianceSsp {
  ssp_name: string; platforms: string[]; total_controls: number; assets_targeted: number;
}
export interface ComplianceOverview {
  env: string; generated_at: string; error?: string;
  fleet: {
    assets: number; total: number; passed: number; failed: number;
    not_applicable: number; not_run: number; evaluated: number; compliance_pct: number;
  };
  by_platform: CompliancePlatform[];
  bands: { good: number; warn: number; poor: number };
  top_failing_controls?: TopFailingControl[];
  asset_count: number; skipped_no_data?: number; assets: ComplianceAsset[];
  ssp_count: number; ssps: ComplianceSsp[];
}
export interface TopFailingControl {
  control_id: string; assets_failing: number; platform?: string; title?: string;
}
export interface ControlDetail {
  asset_id?: string; env?: string; control_id: string; title?: string;
  status?: string; command_executed?: string; evidence?: string; error?: string;
}
export interface AssetControl { control_id: string; title: string; status: string }
export interface AssetControls {
  asset_id?: string; asset_uuid?: string; env?: string; platform?: string;
  catalog?: string; last_scan?: string; status?: string;
  summary?: { total: number; passed: number; failed: number; not_applicable: number; compliance_pct: number };
  controls: AssetControl[]; error?: string;
}

export async function fetchCompliance(env: string): Promise<ComplianceOverview | null> {
  const r = await authedFetch(`/reports/compliance?env=${encodeURIComponent(env)}`);
  if (!r.ok) return null;
  return (await r.json()) as ComplianceOverview;
}

export async function fetchComplianceAsset(asset: string, env: string, status = "failed"): Promise<AssetControls | null> {
  const r = await authedFetch(`/reports/compliance/asset?asset=${encodeURIComponent(asset)}&env=${encodeURIComponent(env)}&status=${status}`);
  if (!r.ok) return null;
  return (await r.json()) as AssetControls;
}

export async function fetchControlDetail(asset: string, control_id: string, env: string): Promise<ControlDetail | null> {
  const r = await authedFetch(`/reports/compliance/control?asset=${encodeURIComponent(asset)}&control_id=${encodeURIComponent(control_id)}&env=${encodeURIComponent(env)}`);
  if (!r.ok) return null;
  return (await r.json()) as ControlDetail;
}

export async function streamComplianceSummary(env: string, onToken: (t: string) => void): Promise<void> {
  const res = await authedFetch(`/reports/compliance/summary?env=${encodeURIComponent(env)}`, { method: "POST" });
  await readTokenStream(res, onToken);
}

export async function refreshFailures(): Promise<FailuresReport | null> {
  const r = await authedFetch("/reports/refresh", { method: "POST" });
  if (!r.ok) return null;
  return (await r.json()) as FailuresReport;
}

export type AnalyzeBody =
  | { type: "pipeline"; project_id: number; pipeline_id: number }
  | { type: "pod"; namespace: string; pod: string };

/** Streams the AI root-cause analysis, calling onToken for each text delta. */
export async function analyze(
  body: AnalyzeBody,
  onToken: (t: string) => void,
): Promise<void> {
  const res = await authedFetch("/reports/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    onToken(`\n_Analysis failed (HTTP ${res.status})._`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        const evt = JSON.parse(line.slice(5).trim());
        if (evt.type === "token") onToken(evt.content as string);
        else if (evt.type === "error") onToken(`\n_${evt.message}_`);
      } catch {
        /* ignore partial */
      }
    }
  }
}
