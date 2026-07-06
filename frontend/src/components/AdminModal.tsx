import { useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  Loader2,
  MemoryStick,
  RefreshCw,
  UserPlus,
  X,
} from "lucide-react";
import {
  createUser,
  fetchStats,
  fetchUsers,
  setUserActive,
  setUserLimit,
  setUserRole,
} from "../lib/admin";
import type { AdminStats, AdminUser } from "../lib/types";

function gb(bytes: number): string {
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3">
      <div className="text-[11px] uppercase tracking-wide text-ops-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold text-ops-text">{value}</div>
    </div>
  );
}

function Bar({ pct }: { pct: number }) {
  const color =
    pct > 90 ? "bg-red-500" : pct > 70 ? "bg-amber-500" : "bg-ops-accent";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-ops-border">
      <div className={`h-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}

export function AdminModal({ onClose }: { onClose: () => void }) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);

  // create-user form
  const [showCreate, setShowCreate] = useState(false);
  const [nEmail, setNEmail] = useState("");
  const [nPass, setNPass] = useState("");
  const [nRole, setNRole] = useState("user");
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);

  const submitCreate = async () => {
    setCreating(true);
    setCreateErr(null);
    const r = await createUser(nEmail.trim(), nPass, nRole);
    setCreating(false);
    if (!r.ok) {
      setCreateErr(r.error || "Failed to create user");
      return;
    }
    setNEmail("");
    setNPass("");
    setNRole("user");
    setShowCreate(false);
    await refresh();
  };

  const refresh = async () => {
    const [s, u] = await Promise.all([fetchStats(), fetchUsers()]);
    setStats(s);
    setUsers(u);
    setLoading(false);
  };

  useEffect(() => {
    refresh();
    // live-refresh just the system/usage stats every 4s
    const id = setInterval(() => {
      fetchStats().then((s) => s && setStats(s));
    }, 4000);
    return () => clearInterval(id);
  }, []);

  const toggleActive = async (u: AdminUser) => {
    await setUserActive(u.id, !u.is_active);
    await refresh();
  };
  const cycleRole = async (u: AdminUser) => {
    const order = ["user", "admin", "guest"];
    const next = order[(order.indexOf(u.role) + 1) % order.length];
    await setUserRole(u.id, next);
    await refresh();
  };
  const editLimit = async (u: AdminUser) => {
    const input = window.prompt(
      `Daily token limit for ${u.email} (0 = unlimited):`,
      String(u.daily_token_limit || 0),
    );
    if (input === null) return;
    const n = parseInt(input, 10);
    if (Number.isNaN(n) || n < 0) return;
    await setUserLimit(u.id, n);
    await refresh();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-ops-border bg-ops-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ops-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-ops-accent" />
            <h2 className="text-sm font-semibold">Admin Dashboard</h2>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={refresh} title="Refresh" className="text-ops-muted hover:text-ops-text">
              <RefreshCw size={15} />
            </button>
            <button onClick={onClose} className="text-ops-muted hover:text-ops-text">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-5">
          {loading || !stats ? (
            <div className="py-10 text-center text-ops-muted">
              <Loader2 size={20} className="mx-auto animate-spin" />
            </div>
          ) : (
            <>
              {/* usage stat cards */}
              <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <StatCard label="Users" value={stats.users} />
                <StatCard label="Documents" value={stats.documents} />
                <StatCard label="Chats" value={stats.chats} />
                <StatCard label="Tokens" value={stats.tokens.toLocaleString()} />
                <StatCard label="Tool calls" value={stats.tool_calls} />
              </div>

              {/* system */}
              <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                    <Cpu size={14} className="text-ops-accent" /> CPU
                    <span className="ml-auto text-ops-muted">
                      {stats.system.cpu_percent}% · {stats.system.cpu_count} cores
                    </span>
                  </div>
                  <Bar pct={stats.system.cpu_percent} />
                  <div className="mt-1 text-[11px] text-ops-muted">
                    load avg: {stats.system.load_avg.map((l) => l.toFixed(2)).join(" · ")}
                  </div>
                </div>
                <div className="rounded-xl border border-ops-border bg-ops-panel/50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                    <MemoryStick size={14} className="text-ops-accent" /> Memory
                    <span className="ml-auto text-ops-muted">
                      {gb(stats.system.mem_used)} / {gb(stats.system.mem_total)} ·{" "}
                      {stats.system.mem_percent}%
                    </span>
                  </div>
                  <Bar pct={stats.system.mem_percent} />
                </div>
              </div>

              {/* model health */}
              <div className="mb-5">
                <div className="mb-2 text-xs font-medium text-ops-muted">Model servers</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries({ ...stats.models, "nomic-embed": stats.embed }).map(
                    ([name, up]) => (
                      <span
                        key={name}
                        className="flex items-center gap-2 rounded-lg border border-ops-border bg-ops-panel px-3 py-1.5 text-sm"
                      >
                        <span
                          className={
                            "h-2 w-2 rounded-full " + (up ? "bg-ops-accent" : "bg-red-500")
                          }
                        />
                        {name}
                        <span className="text-[11px] text-ops-muted">
                          {up ? "up" : "down"}
                        </span>
                      </span>
                    ),
                  )}
                </div>
              </div>

              {/* users */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-medium text-ops-muted">
                    Users ({users.length})
                  </span>
                  <button
                    onClick={() => {
                      setShowCreate((v) => !v);
                      setCreateErr(null);
                    }}
                    className="flex items-center gap-1 rounded-lg border border-ops-border bg-ops-panel px-2.5 py-1 text-xs text-ops-text transition hover:border-ops-accent/50"
                  >
                    <UserPlus size={13} />
                    New user
                  </button>
                </div>

                {showCreate && (
                  <div className="mb-3 rounded-xl border border-ops-border bg-ops-panel/50 p-3">
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                      <input
                        type="email"
                        value={nEmail}
                        onChange={(e) => setNEmail(e.target.value)}
                        placeholder="email"
                        className="rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm outline-none focus:border-ops-accent sm:col-span-2"
                      />
                      <input
                        type="password"
                        value={nPass}
                        onChange={(e) => setNPass(e.target.value)}
                        placeholder="password (8+ chars)"
                        className="rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm outline-none focus:border-ops-accent"
                      />
                      <select
                        value={nRole}
                        onChange={(e) => setNRole(e.target.value)}
                        className="rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm outline-none focus:border-ops-accent"
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                        <option value="guest">guest</option>
                      </select>
                    </div>
                    {createErr && (
                      <div className="mt-2 text-xs text-red-300">{createErr}</div>
                    )}
                    <div className="mt-2 flex justify-end">
                      <button
                        onClick={submitCreate}
                        disabled={creating || !nEmail.trim() || nPass.length < 8}
                        className="rounded-lg bg-ops-accent px-3 py-1.5 text-sm font-medium text-white transition hover:bg-ops-accent-hover disabled:opacity-50"
                      >
                        {creating ? "Creating…" : "Create user"}
                      </button>
                    </div>
                  </div>
                )}
                <div className="overflow-hidden rounded-xl border border-ops-border">
                  <table className="w-full text-sm">
                    <thead className="bg-ops-panel text-left text-[11px] uppercase text-ops-muted">
                      <tr>
                        <th className="px-3 py-2">Email</th>
                        <th className="px-3 py-2">Role</th>
                        <th className="px-3 py-2">Used today / Limit</th>
                        <th className="px-3 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((u) => (
                        <tr key={u.id} className="border-t border-ops-border">
                          <td className="max-w-[220px] truncate px-3 py-2" title={u.email}>
                            {u.email}
                          </td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => cycleRole(u)}
                              title="Click to change role"
                              className="rounded border border-ops-border px-2 py-0.5 text-[11px] uppercase text-ops-muted hover:text-ops-text"
                            >
                              {u.role}
                            </button>
                          </td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => editLimit(u)}
                              title="Click to set daily token limit"
                              className="rounded border border-ops-border px-2 py-0.5 font-mono text-[11px] text-ops-muted hover:text-ops-text"
                            >
                              {u.tokens_used_today.toLocaleString()} /{" "}
                              {u.daily_token_limit
                                ? u.daily_token_limit.toLocaleString()
                                : "∞"}
                            </button>
                          </td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => toggleActive(u)}
                              className={
                                "rounded px-2 py-0.5 text-[11px] " +
                                (u.is_active
                                  ? "bg-ops-accent/20 text-ops-accent"
                                  : "bg-red-950/60 text-red-300")
                              }
                            >
                              {u.is_active ? "active" : "disabled"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
