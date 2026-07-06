import type { ReactNode } from "react";
import { useDashColors } from "./DashTheme";

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  const C = useDashColors();
  return (
    <div className={"rounded-2xl p-4 " + className} style={{ background: C.card, border: `1px solid ${C.border}`, boxShadow: C.dark ? "none" : "0 1px 2px rgba(16,24,40,.04)" }}>
      {title && <div className="mb-3 text-[12px] font-semibold uppercase tracking-wide" style={{ color: C.muted }}>{title}</div>}
      {children}
    </div>
  );
}

export function Kpi({ value, label, tone }: { value: ReactNode; label: string; tone?: string }) {
  const C = useDashColors();
  return (
    <div className="rounded-2xl p-4" style={{ background: C.card, border: `1px solid ${C.border}`, boxShadow: C.dark ? "none" : "0 1px 2px rgba(16,24,40,.04)" }}>
      <div className="text-[26px] font-bold leading-none" style={{ color: tone || C.text }}>{value}</div>
      <div className="mt-1.5 text-[11px] uppercase tracking-wide" style={{ color: C.muted }}>{label}</div>
    </div>
  );
}

export function Pill({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium" style={{ background: color + "1a", color }}>
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {children}
    </span>
  );
}
