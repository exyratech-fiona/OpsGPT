import { useEffect, useRef, useState } from "react";
import { ArrowLeft, BarChart3, Bell, FileDown, LayoutDashboard, Moon, Rocket, ShieldAlert, Sun } from "lucide-react";
import { DashThemeProvider, useDash, useDashColors } from "./DashTheme";
import { DashOverview } from "./DashOverview";
import { DashDelivery } from "./DashDelivery";
import { DashFailures } from "./DashFailures";
import { DashAlerts } from "./DashAlerts";
import { DashReport } from "./DashReport";
import { fetchAlerts } from "../../lib/reports";
import { showAlertNotification } from "../../lib/notify";

type Tab = "overview" | "alerts" | "delivery" | "failures" | "report";
export type DateRange = { from: string; to: string } | null;

const TABS: { id: Tab; label: string; icon: typeof LayoutDashboard; hint: string }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, hint: "Executive summary — live (last 48h failures / 7d delivery)" },
  { id: "alerts", label: "Alerts", icon: Bell, hint: "Live alerts for newly-failed pipelines & pods, each with an AI explanation of the cause and the fix" },
  { id: "delivery", label: "Delivery", icon: Rocket, hint: "Deployments, promotion funnel, change-failure rate, who promoted to real envs — filter by date below" },
  { id: "failures", label: "Reliability", icon: ShieldAlert, hint: "Failed pipelines & pods + AI root-cause — filter pipelines by date below" },
  { id: "report", label: "Report", icon: FileDown, hint: "Generate a board-ready PDF for a date range" },
];

export function Dashboard({ onBack }: { onBack: () => void }) {
  return (
    <DashThemeProvider>
      <DashboardInner onBack={onBack} />
    </DashThemeProvider>
  );
}

function DashboardInner({ onBack }: { onBack: () => void }) {
  const C = useDashColors();
  const { mode, toggle } = useDash();
  const [tab, setTab] = useState<Tab>("overview");
  const [unread, setUnread] = useState(0);
  const active = TABS.find((t) => t.id === tab)!;
  const seenIds = useRef<Set<string> | null>(null);

  // Poll the alert feed so the badge stays live on every tab, and fire a
  // desktop notification for genuinely new failures (primed on first load so
  // the existing backlog doesn't all notify at once).
  useEffect(() => {
    let on = true;
    const tick = async () => {
      const f = await fetchAlerts();
      if (!on || !f) return;
      setUnread(f.unread);
      const ids = new Set(f.alerts.map((a) => a.id));
      if (seenIds.current === null) { seenIds.current = ids; return; }
      const fresh = f.alerts.filter((a) => !a.acked && !seenIds.current!.has(a.id));
      seenIds.current = ids;
      if (fresh.length === 1) {
        showAlertNotification(`OpsGPT — ${fresh[0].kind} failed`, fresh[0].title, fresh[0].id);
      } else if (fresh.length > 1) {
        showAlertNotification(`OpsGPT — ${fresh.length} new failures`, fresh.slice(0, 4).map((a) => `• ${a.title}`).join("\n"), "opsgpt-batch");
      }
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => { on = false; clearInterval(id); };
  }, []);

  const today = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const [from, setFrom] = useState(weekAgo);
  const [to, setTo] = useState(today);
  const [range, setRange] = useState<DateRange>(null);

  const headerStyle = { background: C.card, borderBottom: `1px solid ${C.border}` };
  const dateInput = "rounded-lg px-2 py-1 text-[12px] outline-none";
  const dateInputStyle = { border: `1px solid ${C.border}`, color: C.text, background: C.bg };
  const showDate = tab === "delivery" || tab === "failures";

  return (
    <div className={(mode === "dark" ? "dash-dark" : "dash-light") + " flex h-full min-h-0 flex-1 flex-col"} style={{ background: C.bg, color: C.text }}>
      <div className="flex items-center gap-3 px-6 py-3" style={headerStyle}>
        <button onClick={onBack} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px]" style={{ border: `1px solid ${C.border}`, color: C.muted }}>
          <ArrowLeft size={15} /> Chat
        </button>
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg text-white" style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}>
            <BarChart3 size={16} />
          </span>
          <div>
            <div className="text-[15px] font-bold leading-tight">Delivery &amp; Reliability</div>
            <div className="text-[11px]" style={{ color: C.muted }}>Executive dashboard for engineering leadership</div>
          </div>
        </div>
        <button onClick={toggle} title="Toggle theme" aria-label={mode === "light" ? "Switch to dark theme" : "Switch to light theme"} className="ml-auto flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px]" style={{ border: `1px solid ${C.border}`, color: C.muted }}>
          {mode === "light" ? <Moon size={15} /> : <Sun size={15} />}
          {mode === "light" ? "Dark" : "Light"}
        </button>
      </div>

      <div role="tablist" aria-label="Dashboard sections" className="flex items-center gap-1 px-6 pt-3" style={headerStyle}>
        {TABS.map((t) => {
          const Icon = t.icon;
          const on = t.id === tab;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              role="tab" aria-selected={on} aria-current={on ? "page" : undefined}
              className="flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-medium transition"
              style={{ borderColor: on ? C.accent : "transparent", color: on ? C.text : C.muted }}>
              <Icon size={15} /> {t.label}
              {t.id === "alerts" && unread > 0 && (
                <span className="ml-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 text-[10px] font-bold text-white" style={{ background: C.danger }}>
                  {unread > 99 ? "99+" : unread}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="px-6 py-2 text-[12px]" style={{ background: C.card, color: C.muted, borderBottom: `1px solid ${C.border}` }}>
        {active.hint}
      </div>

      {/* date range filter (Delivery + Reliability) */}
      {showDate && (
        <div className="flex flex-wrap items-center gap-2 px-6 py-2.5 text-[12px]" style={{ background: C.card, borderBottom: `1px solid ${C.border}` }}>
          <button onClick={() => setRange(null)}
            className="rounded-lg px-2.5 py-1 font-medium"
            style={range ? { border: `1px solid ${C.border}`, color: C.muted } : { background: C.accent, color: "#fff" }}>
            ● Live
          </button>
          <span style={{ color: C.muted }}>or date range:</span>
          <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className={dateInput} style={dateInputStyle} />
          <span style={{ color: C.muted }}>→</span>
          <input type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} className={dateInput} style={dateInputStyle} />
          <button onClick={() => setRange({ from, to })} className="rounded-lg px-3 py-1 font-medium text-white" style={{ background: C.accent }}>Apply</button>
          {([["7d", 7], ["30d", 30]] as const).map(([lbl, days]) => (
            <button key={lbl} onClick={() => { const f = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10); setFrom(f); setTo(today); setRange({ from: f, to: today }); }}
              className="rounded-lg px-2 py-1" style={{ border: `1px solid ${C.border}`, color: C.muted }}>{lbl}</button>
          ))}
          {range && <span className="ml-1" style={{ color: C.text }}>Showing {range.from} → {range.to}</span>}
        </div>
      )}

      <div role="tabpanel" aria-label={`${active.label} panel`} className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-5xl">
          {tab === "overview" && <DashOverview />}
          {tab === "alerts" && <DashAlerts onUnread={setUnread} />}
          {tab === "delivery" && <DashDelivery range={range} />}
          {tab === "failures" && <DashFailures range={range} />}
          {tab === "report" && <DashReport />}
        </div>
      </div>
    </div>
  );
}
