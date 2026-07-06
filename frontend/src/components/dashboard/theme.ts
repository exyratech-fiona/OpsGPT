import type { OverviewReport } from "../../lib/reports";

export interface Palette {
  dark: boolean;
  bg: string; card: string; border: string; text: string; muted: string;
  accent: string; ok: string; warn: string; danger: string;
  grid: string; tooltipBg: string; soft: string;
}

// Calm, low-strain palettes. ENV/WORK hues stay the same in both themes.
export const LIGHT: Palette = {
  dark: false,
  bg: "#f4f6fb", card: "#ffffff", border: "#e6e9f2", text: "#1f2937", muted: "#6b7280",
  accent: "#4f46e5", ok: "#16a34a", warn: "#d97706", danger: "#dc2626",
  grid: "#eef1f6", tooltipBg: "#ffffff", soft: "#f3f4f6",
};
export const DARK: Palette = {
  dark: true,
  bg: "#0e1120", card: "#171a2b", border: "#272b42", text: "#e8eaf5", muted: "#9aa0bd",
  accent: "#818cf8", ok: "#34d399", warn: "#fbbf24", danger: "#f87171",
  grid: "#252a40", tooltipBg: "#171a2b", soft: "#1d2136",
};

export const ENV_C: Record<string, string> = {
  DEV: "#6366f1",
  SIT: "#f59e0b",
  DEMO: "#8b5cf6",
  UAT: "#14b8a6",
  PREPROD: "#ec4899",
  PROD: "#10b981",
  OTHER: "#94a3b8",
};

export const WORK_C: Record<string, string> = {
  feature: "#6366f1",
  bugfix: "#ef4444",
  task: "#f59e0b",
  chore: "#64748b",
  other: "#94a3b8",
};

export const ENV_ORDER = ["DEV", "SIT", "DEMO", "UAT", "PREPROD", "PROD", "OTHER"];

export type Insight = { tone: "good" | "warn" | "bad"; text: string };

/** Plain-language takeaways for a CEO/CTO, computed from the numbers. */
export function insights(o: OverviewReport): Insight[] {
  const h = o.headline;
  const out: Insight[] = [];

  out.push({
    tone: h.success_rate >= 85 ? "good" : h.success_rate >= 70 ? "warn" : "bad",
    text: `${h.deploys_window} deployments at ${h.success_rate}% success over ${o.window_days} days — ${
      h.success_rate >= 85 ? "delivery is healthy" : h.success_rate >= 70 ? "some pipeline instability to watch" : "delivery reliability needs attention"
    }.`,
  });

  out.push({
    tone: "good",
    text: `${h.features} new features and ${h.bugfixes} bug fixes shipped — a ${
      h.features >= h.bugfixes ? "feature-led" : "maintenance-heavy"
    } period.`,
  });

  if (h.failing_pods + h.failed_pipelines === 0) {
    out.push({ tone: "good", text: "No failing pods or pipelines right now — systems are green." });
  } else {
    const worst = o.attention.pods[0];
    if (worst) {
      out.push({
        tone: worst.restarts > 1000 ? "bad" : "warn",
        text: `${h.failing_pods} pod${h.failing_pods !== 1 ? "s" : ""} failing; worst is ${worst.pod} (${worst.namespace}) with ${worst.restarts.toLocaleString()} restarts${
          worst.restarts > 1000 ? " — a long-standing outage to prioritise" : ""
        }.`,
      });
    }
    const wp = o.attention.pipelines[0];
    if (wp) {
      out.push({
        tone: "warn",
        text: `${h.failed_pipelines} failed pipelines; ${wp.project.replace(/^DOL\//, "")} fails most (${wp.count}×) — likely a flaky or broken build.`,
      });
    }
  }

  if (o.products[0]) {
    out.push({ tone: "good", text: `${o.products[0].product} is the most active product (${o.products[0].deploys} deploys).` });
  }
  return out.slice(0, 5);
}

export function toEnvData(by_env: Record<string, number>) {
  return ENV_ORDER.filter((e) => by_env[e]).map((e) => ({ name: e, value: by_env[e], fill: ENV_C[e] }));
}
export function toWorkData(work: Record<string, number>) {
  return Object.entries(work).map(([k, v]) => ({ name: k, value: v, fill: WORK_C[k] || WORK_C.other }));
}
export function toDayData(
  per_day: { date: string; by_env: Record<string, number> }[],
): Array<Record<string, string | number>> {
  return per_day.map((d) => ({ date: d.date.slice(5), ...d.by_env }));
}
