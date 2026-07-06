import { useEffect, useState } from "react";
import {
  Boxes,
  CheckCircle2,
  CircleDashed,
  Database,
  Gitlab,
  Loader2,
  Pencil,
  Plug,
  Plus,
  ShieldCheck,
  Star,
  Trash2,
  Wrench,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import {
  createServer,
  deleteServer,
  fetchProviders,
  testConfig,
  testSaved,
  updateServer,
  type McpServer,
} from "../lib/mcp";
import { useAuth } from "../context/AuthContext";

type Field = {
  key: string;
  label: string;
  kind?: "text" | "password" | "textarea" | "checkbox";
  placeholder?: string;
  hint?: string;
};

const FIELDS: Record<string, Field[]> = {
  kubernetes: [
    { key: "kubeconfig", label: "Kubeconfig (YAML)", kind: "textarea", placeholder: "paste a read-only kubeconfig" },
  ],
  elasticsearch: [
    { key: "url", label: "URL", placeholder: "https://host:9200" },
    { key: "username", label: "Username", placeholder: "elastic" },
    { key: "password", label: "Password", kind: "password" },
    { key: "api_key", label: "API key (optional)", kind: "password" },
    { key: "verify_tls", label: "Verify TLS certificate", kind: "checkbox" },
  ],
  gitlab: [
    { key: "url", label: "GitLab URL", placeholder: "https://gitlab.com" },
    { key: "token", label: "Access token (read_api)", kind: "password" },
    { key: "verify_tls", label: "Verify TLS certificate", kind: "checkbox" },
  ],
  grc: [
    { key: "url", label: "Elasticsearch URL", placeholder: "https://host:9200", hint: "The ELK cluster holding grc-ssp-published-* / result / grc-raw-* indices." },
    { key: "username", label: "Username", placeholder: "elastic" },
    { key: "password", label: "Password", kind: "password" },
    { key: "api_key", label: "API key (optional)", kind: "password" },
    { key: "env", label: "Default environment", placeholder: "dev / sit / demo / local", hint: "Used when a question doesn't name an environment." },
    { key: "verify_tls", label: "Verify TLS certificate", kind: "checkbox" },
  ],
};

const PROVIDERS: Record<string, { label: string; Icon: LucideIcon; tint: string }> = {
  kubernetes: { label: "Kubernetes", Icon: Boxes, tint: "text-sky-400" },
  elasticsearch: { label: "Elasticsearch", Icon: Database, tint: "text-amber-400" },
  gitlab: { label: "GitLab", Icon: Gitlab, tint: "text-orange-400" },
  grc: { label: "GRC / Compliance", Icon: ShieldCheck, tint: "text-emerald-400" },
};
const TYPES = Object.keys(PROVIDERS);

function StatusPill({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string; Icon: LucideIcon }> = {
    ok: { label: "Connected", cls: "bg-emerald-500/15 text-emerald-300", Icon: CheckCircle2 },
    error: { label: "Error", cls: "bg-red-500/15 text-red-300", Icon: XCircle },
  };
  const m = map[status] ?? { label: "Not tested", cls: "bg-ops-muted/15 text-ops-muted", Icon: CircleDashed };
  const Icon = m.Icon;
  return (
    <span className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${m.cls}`}>
      <Icon size={11} /> {m.label}
    </span>
  );
}

function ProviderIcon({ type, size = 16 }: { type: string; size?: number }) {
  const p = PROVIDERS[type];
  const Icon = p?.Icon ?? Boxes;
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-ops-border bg-ops-bg">
      <Icon size={size} className={p?.tint ?? "text-ops-accent"} />
    </span>
  );
}

export function McpModal({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);

  // add/edit form
  const [editing, setEditing] = useState<McpServer | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [fType, setFType] = useState("kubernetes");
  const [fName, setFName] = useState("");
  const [fConfig, setFConfig] = useState<Record<string, unknown>>({ verify_tls: true });
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState<{ ok: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setServers(await fetchProviders());
    setLoading(false);
  };
  useEffect(() => {
    refresh();
  }, []);

  const openAdd = () => {
    setEditing(null);
    setFType("kubernetes");
    setFName("");
    setFConfig({ verify_tls: true });
    setTestMsg(null);
    setErr(null);
    setShowForm(true);
  };
  const openEdit = (s: McpServer) => {
    setEditing(s);
    setFType(s.provider_type);
    setFName(s.name);
    setFConfig({ ...s.config });
    setTestMsg(null);
    setErr(null);
    setShowForm(true);
  };

  const runTest = async () => {
    setTesting(true);
    setTestMsg(null);
    try {
      const r = await testConfig(fType, fConfig, editing?.id);
      setTestMsg(r);
    } catch (e) {
      setTestMsg({ ok: false, message: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const cfg = { ...fConfig };
      if (Array.isArray(cfg.projects)) {
        cfg.projects = (cfg.projects as string[]).map((x) => String(x).trim()).filter(Boolean);
      }
      if (editing) await updateServer(editing.id, { name: fName.trim(), config: cfg });
      else await createServer(fName.trim(), fType, cfg);
      setShowForm(false);
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (s: McpServer) => {
    await updateServer(s.id, { enabled: !s.enabled });
    await refresh();
  };
  const onTestSaved = async (s: McpServer) => {
    await testSaved(s.id);
    await refresh();
  };
  const onDelete = async (s: McpServer) => {
    await deleteServer(s.id);
    await refresh();
  };

  // form projects editor (GitLab) — array of project refs, first = default
  const toRefs = (v: unknown): string[] =>
    Array.isArray(v)
      ? v.map(String)
      : typeof v === "string"
        ? v.split(/[\n,]/).map((x) => x.trim()).filter(Boolean)
        : [];
  const projects: string[] = toRefs(fConfig.projects);
  const setProjects = (arr: string[]) => setFConfig((c) => ({ ...c, projects: arr }));

  // chips for a saved server card (default_project first, then watchlist)
  const projectsOf = (s: McpServer): string[] => {
    const out: string[] = [];
    const dp = typeof s.config?.default_project === "string" ? s.config.default_project.trim() : "";
    if (dp) out.push(dp);
    for (const x of [...toRefs(s.config?.projects), ...toRefs(s.config?.favorites)]) {
      if (x && !out.includes(x)) out.push(x);
    }
    return out;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="glass flex max-h-[88vh] w-full max-w-2xl flex-col rounded-2xl border border-ops-border shadow-glow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center justify-between border-b border-ops-border px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gemini shadow-glow">
              <Boxes size={18} className="text-white" />
            </span>
            <div>
              <h2 className="text-sm font-semibold leading-tight">Tool Connections</h2>
              <p className="text-[11px] text-ops-muted">Read-only access to your infrastructure (MCP)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isAdmin && !showForm && (
              <button
                onClick={openAdd}
                className="flex items-center gap-1 rounded-lg bg-gemini px-2.5 py-1.5 text-xs font-medium text-white shadow-glow"
              >
                <Plus size={13} /> Add connection
              </button>
            )}
            <button onClick={onClose} className="text-ops-muted hover:text-ops-text">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto p-5">
          {/* add / edit form */}
          {showForm && (
            <div className="mb-5 rounded-xl border border-ops-border bg-ops-panel/50 p-4">
              {/* type picker (segmented) */}
              <div className="mb-3">
                <label className="mb-1.5 block text-[11px] font-medium text-ops-muted">Provider</label>
                <div className="grid grid-cols-3 gap-2">
                  {TYPES.map((t) => {
                    const p = PROVIDERS[t];
                    const Icon = p.Icon;
                    const active = fType === t;
                    return (
                      <button
                        key={t}
                        disabled={!!editing}
                        onClick={() => {
                          setFType(t);
                          setFConfig({ verify_tls: true });
                          setTestMsg(null);
                        }}
                        className={
                          "flex items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs transition " +
                          (active
                            ? "border-ops-accent bg-ops-accent/10 text-ops-text"
                            : "border-ops-border text-ops-muted hover:border-ops-accent/40") +
                          (editing ? " cursor-not-allowed opacity-60" : "")
                        }
                      >
                        <Icon size={14} className={active ? p.tint : ""} />
                        {p.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* display name */}
              <div className="mb-3">
                <label className="mb-1.5 block text-[11px] font-medium text-ops-muted">Display name</label>
                <input
                  value={fName}
                  onChange={(e) => setFName(e.target.value)}
                  placeholder="e.g. Prod cluster, DevOpsLabs GitLab"
                  className="w-full rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm outline-none focus:border-ops-accent"
                />
              </div>

              {/* type-specific fields */}
              <div className="space-y-3">
                {FIELDS[fType].map((f) => {
                  const setVal = (v: unknown) => setFConfig((c) => ({ ...c, [f.key]: v }));
                  const secretSet = (fConfig as Record<string, unknown>)[`${f.key}_set`];
                  if (f.kind === "checkbox") {
                    return (
                      <label key={f.key} className="flex items-center gap-2 text-sm text-ops-text">
                        <input
                          type="checkbox"
                          checked={Boolean(fConfig[f.key])}
                          onChange={(e) => setVal(e.target.checked)}
                          className="accent-ops-accent"
                        />
                        {f.label}
                      </label>
                    );
                  }
                  return (
                    <div key={f.key}>
                      <label className="mb-1.5 block text-[11px] font-medium text-ops-muted">{f.label}</label>
                      {f.kind === "textarea" ? (
                        <textarea
                          value={String(fConfig[f.key] ?? "")}
                          onChange={(e) => setVal(e.target.value)}
                          placeholder={editing && secretSet ? "•••• unchanged — paste to replace" : f.placeholder}
                          rows={f.key === "kubeconfig" ? 5 : 3}
                          className="w-full rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 font-mono text-[11px] outline-none focus:border-ops-accent"
                        />
                      ) : (
                        <input
                          type={f.kind === "password" ? "password" : "text"}
                          value={String(fConfig[f.key] ?? "")}
                          onChange={(e) => setVal(e.target.value)}
                          placeholder={editing && f.kind === "password" && secretSet ? "•••• unchanged" : f.placeholder}
                          className="w-full rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm outline-none focus:border-ops-accent"
                        />
                      )}
                      {f.hint && <p className="mt-1 text-[10px] text-ops-muted">{f.hint}</p>}
                    </div>
                  );
                })}
              </div>

              {/* GitLab: multi-project watchlist */}
              {fType === "gitlab" && (
                <div className="mt-3">
                  <label className="mb-1.5 block text-[11px] font-medium text-ops-muted">Projects</label>
                  <div className="space-y-1.5">
                    {projects.length === 0 && (
                      <p className="text-[11px] text-ops-muted">No projects yet — add the ones you want to watch.</p>
                    )}
                    {projects.map((p, i) => (
                      <div key={i} className="flex items-center gap-2">
                        {i === 0 ? (
                          <span title="Default project" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-ops-accent/50 bg-ops-accent/10">
                            <Star size={12} className="text-ops-accent" />
                          </span>
                        ) : (
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center text-[10px] text-ops-muted">{i + 1}</span>
                        )}
                        <input
                          value={p}
                          onChange={(e) => {
                            const a = [...projects];
                            a[i] = e.target.value;
                            setProjects(a);
                          }}
                          placeholder="id, group/subgroup/project, or a pasted URL"
                          className="flex-1 rounded-lg border border-ops-border bg-ops-bg px-2.5 py-1.5 text-sm outline-none focus:border-ops-accent"
                        />
                        <button
                          onClick={() => setProjects(projects.filter((_, j) => j !== i))}
                          className="text-ops-muted hover:text-red-400"
                          title="Remove"
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={() => setProjects([...projects, ""])}
                    className="mt-2 flex items-center gap-1 rounded-lg border border-ops-border px-2.5 py-1 text-xs text-ops-text hover:border-ops-accent/50"
                  >
                    <Plus size={12} /> Add project
                  </button>
                  <p className="mt-1.5 text-[10px] text-ops-muted">
                    The first (★) is the default when a question doesn't name a project. Ask
                    “show the latest pipelines” and the assistant lists the most recent pipeline for
                    every project here.
                  </p>
                </div>
              )}

              {testMsg && (
                <div
                  className={
                    "mt-3 flex items-center gap-2 rounded-lg px-3 py-2 text-sm " +
                    (testMsg.ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-950/40 text-red-300")
                  }
                >
                  {testMsg.ok ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                  {testMsg.message}
                </div>
              )}
              {err && <div className="mt-2 text-xs text-red-300">{err}</div>}

              <div className="mt-4 flex items-center justify-end gap-2">
                <button onClick={() => setShowForm(false)} className="rounded-lg px-3 py-1.5 text-sm text-ops-muted hover:text-ops-text">
                  Cancel
                </button>
                <button
                  onClick={runTest}
                  disabled={testing}
                  className="flex items-center gap-1 rounded-lg border border-ops-border px-3 py-1.5 text-sm text-ops-text hover:border-ops-accent/50 disabled:opacity-50"
                >
                  {testing ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />}
                  Test connection
                </button>
                <button
                  onClick={save}
                  disabled={saving || !fName.trim()}
                  className="rounded-lg bg-gemini px-3 py-1.5 text-sm font-medium text-white shadow-glow disabled:opacity-50"
                >
                  {saving ? "Saving…" : editing ? "Save changes" : "Add"}
                </button>
              </div>
            </div>
          )}

          {/* server list */}
          {loading ? (
            <div className="py-10 text-center text-ops-muted">
              <Loader2 size={18} className="mx-auto animate-spin" />
            </div>
          ) : servers.length === 0 ? (
            <div className="py-10 text-center">
              <Boxes size={26} className="mx-auto mb-2 text-ops-muted" />
              <p className="text-xs text-ops-muted">No tool connections yet.</p>
              {isAdmin && <p className="mt-1 text-[11px] text-ops-muted">Click “Add connection” to wire up Kubernetes, Elasticsearch or GitLab.</p>}
            </div>
          ) : (
            <div className="space-y-3">
              {servers.map((s) => {
                const projs = projectsOf(s);
                return (
                  <div key={s.id} className="rounded-xl border border-ops-border bg-ops-panel/50 p-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-3">
                        <ProviderIcon type={s.provider_type} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="truncate text-sm font-medium">{s.name}</span>
                            {!s.enabled && (
                              <span className="rounded bg-red-950/50 px-1.5 text-[10px] text-red-300">off</span>
                            )}
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            <span className="text-[11px] text-ops-muted">{s.display_name}</span>
                            <StatusPill status={s.status} />
                          </div>
                        </div>
                      </div>
                      {isAdmin && (
                        <div className="flex items-center gap-2">
                          <button onClick={() => onTestSaved(s)} title="Test connection" className="text-ops-muted hover:text-ops-text">
                            <Plug size={15} />
                          </button>
                          <button
                            onClick={() => toggle(s)}
                            title={s.enabled ? "Disable" : "Enable"}
                            className={"relative h-5 w-9 rounded-full transition " + (s.enabled ? "bg-ops-accent" : "bg-ops-border")}
                          >
                            <span className={"absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all " + (s.enabled ? "left-[18px]" : "left-0.5")} />
                          </button>
                          <button onClick={() => openEdit(s)} className="text-ops-muted hover:text-ops-text" title="Edit">
                            <Pencil size={14} />
                          </button>
                          <button onClick={() => onDelete(s)} className="text-ops-muted hover:text-red-400" title="Delete">
                            <Trash2 size={15} />
                          </button>
                        </div>
                      )}
                    </div>

                    {s.status_message && (
                      <p className={"mt-2 text-[11px] " + (s.status === "error" ? "text-red-300" : "text-ops-muted")}>
                        {s.status_message}
                      </p>
                    )}

                    {projs.length > 0 && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        {projs.map((p, i) => (
                          <span
                            key={p}
                            title={i === 0 ? "Default project" : undefined}
                            className={
                              "flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-[10px] " +
                              (i === 0
                                ? "border-ops-accent/50 bg-ops-accent/10 text-ops-text"
                                : "border-ops-border bg-ops-bg text-ops-muted")
                            }
                          >
                            {i === 0 && <Star size={9} className="text-ops-accent" />}
                            {p}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-ops-border/60 pt-2.5">
                      {s.tools.map((t) => (
                        <span key={t.name} title={t.description} className="flex items-center gap-1 rounded-md border border-ops-border bg-ops-bg px-2 py-0.5 font-mono text-[10px] text-ops-muted">
                          <Wrench size={9} className="text-ops-accent" />
                          {t.name}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {!isAdmin && (
            <p className="mt-4 text-center text-[11px] text-ops-muted">
              Tool connections are managed by an admin. Enabled ones are used automatically when relevant.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
