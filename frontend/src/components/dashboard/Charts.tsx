import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ENV_C, ENV_ORDER, toDayData, toEnvData, toWorkData } from "./theme";
import { useDashColors } from "./DashTheme";

function useChartBits() {
  const C = useDashColors();
  return {
    C,
    axis: { fontSize: 11, fill: C.muted },
    grid: C.grid,
    tip: {
      contentStyle: { borderRadius: 10, border: `1px solid ${C.border}`, background: C.tooltipBg, fontSize: 12 },
      itemStyle: { color: C.text },
      labelStyle: { color: C.muted, fontWeight: 600, marginBottom: 2 },
      cursor: { fill: C.soft },
    },
  };
}

export function EnvBar({ by_env, height = 220 }: { by_env: Record<string, number>; height?: number }) {
  const { axis, grid, tip } = useChartBits();
  const data = toEnvData(by_env);
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
        <XAxis dataKey="name" tick={axis} axisLine={false} tickLine={false} />
        <YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip {...tip} />
        <Bar dataKey="value" radius={[6, 6, 0, 0]} name="deploys">
          {data.map((d) => <Cell key={d.name} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function WorkPie({ work, height = 220 }: { work: Record<string, number>; height?: number }) {
  const { C, tip } = useChartBits();
  const data = toWorkData(work).filter((d) => d.value > 0);
  if (!data.length) return <Empty label="No merged work in range" />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={82} paddingAngle={2} stroke="none">
          {data.map((d) => <Cell key={d.name} fill={d.fill} />)}
        </Pie>
        <Tooltip {...tip} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: C.muted }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function DayTrend({ per_day, height = 240 }: { per_day: { date: string; by_env: Record<string, number> }[]; height?: number }) {
  const { C, axis, grid, tip } = useChartBits();
  const data = toDayData(per_day);
  if (!data.length) return <Empty />;
  const envs = ENV_ORDER.filter((e) => data.some((d) => d[e]));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
        <XAxis dataKey="date" tick={axis} axisLine={false} tickLine={false} />
        <YAxis tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip {...tip} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: 11, color: C.muted }} />
        {envs.map((e, i) => (
          <Bar key={e} dataKey={e} stackId="a" fill={ENV_C[e]} radius={i === envs.length - 1 ? [5, 5, 0, 0] : undefined} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ProductBar({ products, height = 260 }: { products: { product: string; deploys: number }[]; height?: number }) {
  const { C, axis, grid, tip } = useChartBits();
  const data = products.slice(0, 8).map((p) => ({ name: p.product.length > 16 ? p.product.slice(0, 15) + "…" : p.product, deploys: p.deploys }));
  if (!data.length) return <Empty />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart layout="vertical" data={data} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} horizontal={false} />
        <XAxis type="number" tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
        <YAxis type="category" dataKey="name" tick={axis} axisLine={false} tickLine={false} width={120} />
        <Tooltip {...tip} />
        <Bar dataKey="deploys" fill={C.accent} radius={[0, 6, 6, 0]} barSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bar: who promoted the most distinct changes to REAL environments. */
export function PeopleBar({ people, height = 220 }: { people: { user: string; real: number }[]; height?: number }) {
  const { C, axis, grid, tip } = useChartBits();
  const data = people.filter((p) => p.real > 0).slice(0, 8)
    .map((p) => ({ name: p.user.length > 16 ? p.user.slice(0, 15) + "…" : p.user, real: p.real }));
  if (!data.length) return <Empty label="No real-environment promotions in range" />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart layout="vertical" data={data} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={grid} horizontal={false} />
        <XAxis type="number" tick={axis} axisLine={false} tickLine={false} allowDecimals={false} />
        <YAxis type="category" dataKey="name" tick={axis} axisLine={false} tickLine={false} width={120} />
        <Tooltip {...tip} />
        <Bar dataKey="real" name="real-env promotions" fill={C.ok} radius={[0, 6, 6, 0]} barSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function Empty({ label = "No data" }: { label?: string }) {
  const C = useDashColors();
  return <div className="flex h-[180px] items-center justify-center text-sm" style={{ color: C.muted }}>{label}</div>;
}
