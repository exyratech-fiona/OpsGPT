import { useCallback, useEffect, useState } from "react";
import { Bell, BellOff, BellRing, Boxes, Check, ChevronDown, ChevronRight, ExternalLink, GitBranch, Loader2, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { ackAlert, clearAlerts, fetchAlerts, scanAlerts, type Alert } from "../../lib/reports";
import { ensureNotifyPermission, notifyPermission, notifySupported, showAlertNotification } from "../../lib/notify";
import { Markdown } from "../Markdown";
import { useAuth } from "../../context/AuthContext";
import { useDashColors } from "./DashTheme";
import { Card } from "./ui";

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function hoursBetween(a?: string | null, b?: string | null): number {
  if (!a || !b) return 0;
  const ta = Date.parse(a), tb = Date.parse(b);
  if (Number.isNaN(ta) || Number.isNaN(tb)) return 0;
  return Math.abs(ta - tb) / 3600000;
}

export function DashAlerts({ onUnread }: { onUnread?: (n: number) => void }) {
  const C = useDashColors();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [perm, setPerm] = useState<NotificationPermission>(notifyPermission());

  const enableNotify = async () => {
    const p = await ensureNotifyPermission();
    setPerm(p);
    if (p === "granted") showAlertNotification("OpsGPT alerts enabled", "You'll be notified here the moment a pipeline or pod fails.", "opsgpt-test");
  };

  const load = useCallback(async () => {
    const f = await fetchAlerts();
    if (f) {
      setAlerts(f.alerts);
      onUnread?.(f.unread);
    }
  }, [onUnread]);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const scan = async () => {
    setScanning(true);
    await scanAlerts();
    await load();
    setScanning(false);
  };
  const ack = async (id: string | null) => {
    const f = await ackAlert(id);
    if (f) { setAlerts(f.alerts); onUnread?.(f.unread); }
  };
  const clear = async () => {
    const f = await clearAlerts();
    if (f) { setAlerts(f.alerts); onUnread?.(f.unread); }
  };

  if (!alerts)
    return (
      <div className="py-20 text-center" style={{ color: C.muted }}>
        <Loader2 size={22} className="mx-auto animate-spin" />
        <p className="mt-2 text-sm">Loading alerts…</p>
      </div>
    );

  const unread = alerts.filter((a) => !a.acked).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: C.text }}>
          <Bell size={16} style={{ color: unread ? C.danger : C.muted }} />
          {unread ? `${unread} new alert${unread > 1 ? "s" : ""}` : "No new alerts"}
          <span className="text-[12px] font-normal" style={{ color: C.muted }}>· {alerts.length} in feed</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {notifySupported() && perm !== "granted" && (
            <button onClick={enableNotify} disabled={perm === "denied"}
              title={perm === "denied" ? "Notifications are blocked — enable them for this site in your browser settings" : "Get a desktop notification when something fails"}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] disabled:opacity-50" style={{ border: `1px solid ${C.border}`, color: perm === "denied" ? C.muted : C.accent }}>
              <BellRing size={13} /> {perm === "denied" ? "Notifications blocked" : "Enable desktop alerts"}
            </button>
          )}
          {isAdmin && (
            <button onClick={scan} disabled={scanning} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px]" style={{ border: `1px solid ${C.border}`, color: C.text }}>
              <RefreshCw size={13} className={scanning ? "animate-spin" : ""} /> Check now
            </button>
          )}
          {unread > 0 && (
            <button onClick={() => ack(null)} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px]" style={{ border: `1px solid ${C.border}`, color: C.text }}>
              <Check size={13} /> Mark all read
            </button>
          )}
          {isAdmin && alerts.length > 0 && (
            <button onClick={clear} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px]" style={{ border: `1px solid ${C.border}`, color: C.danger }}>
              <Trash2 size={13} /> Clear
            </button>
          )}
        </div>
      </div>

      {alerts.length === 0 && (
        <Card>
          <div className="flex flex-col items-center gap-2 py-10 text-center" style={{ color: C.muted }}>
            <BellOff size={26} />
            <p className="text-sm">All quiet — no failures detected.</p>
            <p className="text-[12px]">OpsGPT watches GitLab pipelines &amp; Kubernetes pods every couple of minutes and will raise an alert here (with the cause and the fix) the moment something new breaks.</p>
          </div>
        </Card>
      )}

      {alerts.map((a) => {
        const isPod = a.kind === "pod";
        const Icon = isPod ? Boxes : GitBranch;
        const tone = isPod ? C.danger : C.warn;
        const isOpen = open[a.id] ?? !a.acked; // new alerts start expanded
        const failedAt = a.created_at || a.detected_at;
        const preexisting = hoursBetween(a.created_at, a.detected_at) > 1; // failed well before we first saw it
        return (
          <div key={a.id} className="rounded-2xl p-4"
            style={{ background: C.card, border: `1px solid ${a.acked ? C.border : tone}`, boxShadow: C.dark ? "none" : "0 1px 2px rgba(16,24,40,.04)" }}>
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg" style={{ background: tone + "1a", color: tone }}>
                <Icon size={15} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide" style={{ background: tone + "1a", color: tone }}>
                    {isPod ? "Pod" : "Pipeline"}
                  </span>
                  {!a.acked && <span className="h-2 w-2 rounded-full" style={{ background: C.danger }} title="new" />}
                  {preexisting && (
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-medium" style={{ background: C.muted + "22", color: C.muted }} title="This was already failing before monitoring started — a long-standing issue, not a fresh break.">
                      pre-existing
                    </span>
                  )}
                  <span className="ml-auto whitespace-nowrap text-right text-[11px]" style={{ color: C.muted }}>
                    <span title={failedAt || ""}>failed {timeAgo(failedAt)}</span>
                    {preexisting && <span className="block opacity-70" title={`OpsGPT first detected this ${a.detected_at}`}>caught {timeAgo(a.detected_at)}</span>}
                  </span>
                </div>
                <div className="mt-1 truncate text-[14px] font-semibold" style={{ color: C.text }} title={a.title}>{a.title}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px]" style={{ color: C.muted }}>
                  {isPod ? (
                    <>
                      <span className="rounded px-1.5 py-0.5" style={{ background: C.bg }}>{a.namespace}</span>
                      {a.reason && <span style={{ color: C.danger }}>{a.reason}</span>}
                      {a.restarts != null && <span>{a.restarts.toLocaleString()} restarts</span>}
                    </>
                  ) : (
                    <>
                      {a.pipeline_id && <span>#{a.pipeline_id}</span>}
                      {a.ref && <span className="flex items-center gap-1"><GitBranch size={10} />{a.ref}</span>}
                      {a.web_url && <a href={a.web_url} target="_blank" rel="noreferrer" className="flex items-center gap-0.5" style={{ color: C.accent }}>open in GitLab <ExternalLink size={10} /></a>}
                    </>
                  )}
                </div>
              </div>
            </div>

            <button onClick={() => setOpen((o) => ({ ...o, [a.id]: !isOpen }))}
              className="mt-3 flex items-center gap-1.5 text-[12px] font-medium" style={{ color: C.accent }}>
              {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <Sparkles size={13} /> {isOpen ? "Hide" : "Show"} AI cause &amp; fix
            </button>

            {isOpen && (
              <div className="mt-2 rounded-xl p-3" style={{ background: C.bg }}>
                {a.analysis ? (
                  <div className="dash-analysis text-[13px]"><Markdown content={a.analysis} /></div>
                ) : (
                  <p className="text-[12px]" style={{ color: C.muted }}>No analysis was captured for this alert.</p>
                )}
              </div>
            )}

            {!a.acked && (
              <div className="mt-3 flex justify-end">
                <button onClick={() => ack(a.id)} className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[12px]" style={{ border: `1px solid ${C.border}`, color: C.muted }}>
                  <Check size={12} /> Acknowledge
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
