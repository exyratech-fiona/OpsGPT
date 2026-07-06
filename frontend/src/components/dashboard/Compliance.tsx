import { ArrowLeft, Moon, ShieldCheck, Sun } from "lucide-react";
import { DashThemeProvider, useDash, useDashColors } from "./DashTheme";
import { DashCompliance } from "./DashCompliance";
import { ChatbotWidget } from "./ChatbotWidget";

/** Standalone top-level Compliance page (its own sidebar entry, not a Dashboard tab). */
export function Compliance({ onBack }: { onBack: () => void }) {
  return (
    <DashThemeProvider>
      <Inner onBack={onBack} />
    </DashThemeProvider>
  );
}

function Inner({ onBack }: { onBack: () => void }) {
  const C = useDashColors();
  const { mode, toggle } = useDash();
  return (
    <div className={(mode === "dark" ? "dash-dark" : "dash-light") + " flex h-full min-h-0 flex-1 flex-col"} style={{ background: C.bg, color: C.text }}>
      <div className="flex items-center gap-3 px-6 py-3" style={{ background: C.card, borderBottom: `1px solid ${C.border}` }}>
        <button onClick={onBack} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px]" style={{ border: `1px solid ${C.border}`, color: C.muted }}>
          <ArrowLeft size={15} /> Chat
        </button>
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg text-white" style={{ background: "linear-gradient(135deg,#10b981,#059669)" }}>
            <ShieldCheck size={16} />
          </span>
          <div>
            <div className="text-[15px] font-bold leading-tight">Compliance</div>
            <div className="text-[11px]" style={{ color: C.muted }}>GRC posture from your ELK scans</div>
          </div>
        </div>
        <button onClick={toggle} title="Toggle theme" aria-label={mode === "light" ? "Switch to dark theme" : "Switch to light theme"} className="ml-auto flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px]" style={{ border: `1px solid ${C.border}`, color: C.muted }}>
          {mode === "light" ? <Moon size={15} /> : <Sun size={15} />}
          {mode === "light" ? "Dark" : "Light"}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-5xl">
          <DashCompliance />
        </div>
      </div>
      <ChatbotWidget />
    </div>
  );
}
