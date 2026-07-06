import type { Customer } from "../../lib/reports";
import { useDashColors } from "./DashTheme";
import { Card } from "./ui";

export function CustomerCard({ customers }: { customers: Customer[] }) {
  const C = useDashColors();
  const max = Math.max(1, ...customers.map((c) => c.deploys));
  return (
    <Card title="By customer / account">
      <div className="overflow-x-auto">
        <table className="w-full text-[12.5px]">
          <thead>
            <tr style={{ color: C.muted }}>
              <th className="px-2 py-1.5 text-left font-medium">Customer</th>
              <th className="px-2 py-1.5 text-right font-medium">Deploys</th>
              <th className="px-2 py-1.5 text-right font-medium">Real env</th>
              <th className="px-2 py-1.5 text-right font-medium">Failed</th>
              <th className="px-2 py-1.5 text-right font-medium">MRs</th>
              <th className="px-2 py-1.5 text-right font-medium">Projects</th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 && (
              <tr><td className="px-2 py-2" style={{ color: C.muted }} colSpan={6}>No deployments in range.</td></tr>
            )}
            {customers.map((c) => {
              const failed = c.failed_pipelines ?? c.failed;
              return (
                <tr key={c.customer} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td className="px-2 py-1.5 font-medium" style={{ color: C.text }}>{c.customer}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-2 rounded-full" style={{ width: `${(60 * c.deploys) / max}px`, minWidth: "4px", background: C.accent }} />
                      <span style={{ color: C.text }}>{c.deploys}</span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5 text-right font-semibold" style={{ color: c.real ? C.ok : C.muted }}>{c.real}</td>
                  <td className="px-2 py-1.5 text-right" style={{ color: failed ? C.danger : C.muted }}>{failed}</td>
                  <td className="px-2 py-1.5 text-right" style={{ color: C.muted }}>{c.mrs}</td>
                  <td className="px-2 py-1.5 text-right" style={{ color: C.muted }}>{c.projects}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
