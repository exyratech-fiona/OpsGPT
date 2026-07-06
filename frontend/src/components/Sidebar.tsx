import { useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Boxes,
  FileText,
  KeyRound,
  LogOut,
  MessageSquarePlus,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import clsx from "clsx";
import type { Conversation } from "../lib/types";
import { useAuth } from "../context/AuthContext";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  open: boolean;
  onClose: () => void;
  onOpenKeys: () => void;
  onOpenMcp: () => void;
  onOpenDocs: () => void;
  onOpenAdmin: () => void;
  onOpenReports: () => void;
  onOpenCompliance: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  onNew,
  onSelect,
  onDelete,
  open,
  onClose,
  onOpenKeys,
  onOpenMcp,
  onOpenDocs,
  onOpenAdmin,
  onOpenReports,
  onOpenCompliance,
}: Props) {
  const { user, logout } = useAuth();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
    if (!q) return list;
    return list.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.messages.some((m) => m.content.toLowerCase().includes(q)),
    );
  }, [conversations, query]);

  return (
    <>
      {/* mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/50 md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={clsx(
          "glass fixed z-30 flex h-full w-72 flex-col border-r border-ops-border transition-transform md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between p-3">
          <div className="flex items-center gap-2 px-1">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gemini text-sm font-bold text-white shadow-glow">
              O
            </div>
            <span className="text-sm font-bold tracking-tight text-gradient">OpsGPT</span>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-ops-muted hover:text-ops-text md:hidden"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-1.5 px-3">
          <button
            onClick={onNew}
            className="flex w-full items-center gap-2 rounded-lg border border-ops-border bg-ops-panel px-3 py-2 text-sm font-medium text-ops-text transition hover:border-ops-accent/50"
          >
            <MessageSquarePlus size={16} />
            New chat
          </button>
          <button
            onClick={onOpenMcp}
            className="flex w-full items-center gap-2 rounded-lg border border-ops-border bg-ops-panel px-3 py-2 text-sm font-medium text-ops-text transition hover:border-ops-accent/50"
          >
            <Boxes size={16} className="text-ops-accent" />
            MCP · Tools
          </button>
          <button
            onClick={onOpenReports}
            className="flex w-full items-center gap-2 rounded-lg border border-ops-border bg-ops-panel px-3 py-2 text-sm font-medium text-ops-text transition hover:border-ops-accent/50"
          >
            <BarChart3 size={16} className="text-ops-accent" />
            Dashboard
          </button>
          <button
            onClick={onOpenCompliance}
            className="flex w-full items-center gap-2 rounded-lg border border-ops-border bg-ops-panel px-3 py-2 text-sm font-medium text-ops-text transition hover:border-ops-accent/50"
          >
            <ShieldCheck size={16} className="text-emerald-400" />
            Compliance
          </button>
        </div>

        <div className="px-3 pb-2 pt-3">
          <div className="flex items-center gap-2 rounded-lg bg-ops-panel px-3 py-1.5">
            <Search size={14} className="text-ops-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search chats"
              className="w-full bg-transparent text-sm text-ops-text placeholder:text-ops-muted focus:outline-none"
            />
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {filtered.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-ops-muted">
              {query ? "No matches" : "No conversations yet"}
            </p>
          )}
          {filtered.map((c) => (
            <div
              key={c.id}
              className={clsx(
                "group flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                c.id === activeId
                  ? "bg-ops-panel text-ops-text"
                  : "text-ops-muted hover:bg-ops-panel/60 hover:text-ops-text",
              )}
            >
              <button
                onClick={() => onSelect(c.id)}
                className="min-w-0 flex-1 truncate text-left"
                title={c.title}
              >
                {c.title}
              </button>
              <button
                onClick={() => onDelete(c.id)}
                className="opacity-0 transition group-hover:opacity-100"
                title="Delete"
              >
                <Trash2 size={14} className="text-ops-muted hover:text-red-400" />
              </button>
            </div>
          ))}
        </nav>

        <div className="border-t border-ops-border p-2">
          {user?.role === "admin" && (
            <button
              onClick={onOpenAdmin}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ops-muted transition hover:bg-ops-panel/60 hover:text-ops-text"
            >
              <Activity size={15} />
              Admin
            </button>
          )}
          <button
            onClick={onOpenDocs}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ops-muted transition hover:bg-ops-panel/60 hover:text-ops-text"
          >
            <FileText size={15} />
            Documents
          </button>
          <button
            onClick={onOpenKeys}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ops-muted transition hover:bg-ops-panel/60 hover:text-ops-text"
          >
            <KeyRound size={15} />
            API Keys
          </button>
          <div className="mt-1 flex items-center gap-2 rounded-lg px-3 py-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ops-panel text-xs font-semibold uppercase text-ops-text">
              {user?.email.charAt(0) ?? "?"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs text-ops-text" title={user?.email}>
                {user?.email}
              </div>
              <div className="text-[10px] uppercase tracking-wide text-ops-muted">
                {user?.role}
              </div>
            </div>
            <button
              onClick={logout}
              title="Log out"
              className="text-ops-muted hover:text-red-400"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
