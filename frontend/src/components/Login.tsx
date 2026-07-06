import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";

type Tab = "login" | "register";

export function Login() {
  const { login, register } = useAuth();
  const [tab, setTab] = useState<Tab>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (tab === "login") await login(email, password);
      else await register(email, password);
    } catch (err) {
      setError((err as Error).message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full w-full items-center justify-center bg-ops-bg px-4">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="mb-6 flex flex-col items-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gemini text-2xl font-bold text-white shadow-glow-lg">
            O
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-gradient">OpsGPT</h1>
          <p className="text-sm text-ops-muted">Self-hosted AI for DevOps</p>
        </div>

        <div className="glass gradient-border rounded-2xl p-6 shadow-glow-lg">
          <div className="mb-5 flex rounded-lg bg-ops-panel p-1">
            {(["login", "register"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => {
                  setTab(t);
                  setError(null);
                }}
                className={
                  "flex-1 rounded-md py-1.5 text-sm font-medium capitalize transition " +
                  (tab === t
                    ? "bg-gemini text-white shadow-glow"
                    : "text-ops-muted hover:text-ops-text")
                }
              >
                {t === "register" ? "Sign up" : "Log in"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-ops-muted">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-lg border border-ops-border bg-ops-bg px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ops-muted">Password</label>
              <input
                type="password"
                required
                minLength={tab === "register" ? 8 : 1}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={tab === "register" ? "At least 8 characters" : "••••••••"}
                className="w-full rounded-lg border border-ops-border bg-ops-bg px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-gemini py-2 text-sm font-medium text-white shadow-glow transition hover:opacity-90 disabled:opacity-50"
            >
              {busy && <Loader2 size={15} className="animate-spin" />}
              {tab === "login" ? "Log in" : "Create account"}
            </button>
          </form>
        </div>
        <p className="mt-4 text-center text-xs text-ops-muted">
          Self-hosted · your data never leaves your server
        </p>
      </div>
    </div>
  );
}
