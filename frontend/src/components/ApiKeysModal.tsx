import { useEffect, useState } from "react";
import { Check, Copy, KeyRound, Loader2, Plus, Trash2, X } from "lucide-react";
import {
  createKey,
  listKeys,
  revokeKey,
  type ApiKey,
  type ApiKeyCreated,
} from "../lib/keys";

export function ApiKeysModal({ onClose }: { onClose: () => void }) {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const refresh = async () => {
    setKeys(await listKeys());
    setLoading(false);
  };

  useEffect(() => {
    refresh();
  }, []);

  const onCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const k = await createKey(name.trim());
      setCreated(k);
      setName("");
      await refresh();
    } finally {
      setCreating(false);
    }
  };

  const onRevoke = async (id: string) => {
    await revokeKey(id);
    await refresh();
  };

  const copyKey = async () => {
    if (!created) return;
    await navigator.clipboard.writeText(created.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-ops-border bg-ops-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ops-border px-5 py-3">
          <div className="flex items-center gap-2">
            <KeyRound size={16} className="text-ops-accent" />
            <h2 className="text-sm font-semibold">API Keys</h2>
          </div>
          <button onClick={onClose} className="text-ops-muted hover:text-ops-text">
            <X size={18} />
          </button>
        </div>

        <div className="p-5">
          <p className="mb-3 text-xs text-ops-muted">
            Use an API key for programmatic access (OpenAI-compatible). Send it as
            <code className="mx-1 rounded bg-ops-panel px-1">Authorization: Bearer opsk_…</code>
          </p>

          {created && (
            <div className="mb-4 rounded-lg border border-ops-accent/40 bg-ops-accent/10 p-3">
              <p className="mb-1 text-xs text-ops-text">
                Copy your new key now — it won't be shown again:
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 truncate rounded bg-ops-bg px-2 py-1 font-mono text-xs">
                  {created.key}
                </code>
                <button
                  onClick={copyKey}
                  className="flex items-center gap-1 rounded bg-ops-accent px-2 py-1 text-xs text-white"
                >
                  {copied ? <Check size={12} /> : <Copy size={12} />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
          )}

          <div className="mb-4 flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Key name (e.g. ci-pipeline)"
              className="flex-1 rounded-lg border border-ops-border bg-ops-bg px-3 py-2 text-sm outline-none focus:border-ops-accent"
            />
            <button
              onClick={onCreate}
              disabled={creating || !name.trim()}
              className="flex items-center gap-1 rounded-lg bg-ops-accent px-3 py-2 text-sm font-medium text-white transition hover:bg-ops-accent-hover disabled:opacity-50"
            >
              {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Create
            </button>
          </div>

          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {loading ? (
              <div className="py-6 text-center text-ops-muted">
                <Loader2 size={18} className="mx-auto animate-spin" />
              </div>
            ) : keys.length === 0 ? (
              <p className="py-6 text-center text-xs text-ops-muted">No API keys yet</p>
            ) : (
              keys.map((k) => (
                <div
                  key={k.id}
                  className="flex items-center justify-between rounded-lg border border-ops-border bg-ops-panel px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="truncate font-medium">{k.name}</span>
                      {k.revoked && (
                        <span className="rounded bg-red-950/60 px-1.5 text-[10px] text-red-300">
                          revoked
                        </span>
                      )}
                    </div>
                    <code className="font-mono text-[11px] text-ops-muted">
                      {k.prefix}…
                    </code>
                  </div>
                  {!k.revoked && (
                    <button
                      onClick={() => onRevoke(k.id)}
                      title="Revoke"
                      className="text-ops-muted hover:text-red-400"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
