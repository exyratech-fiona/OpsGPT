import { useState } from "react";
import { Loader2, PanelLeft } from "lucide-react";
import { Sidebar } from "./components/Sidebar";
import { ChatWindow } from "./components/ChatWindow";
import { Composer } from "./components/Composer";
import { Login } from "./components/Login";
import { ApiKeysModal } from "./components/ApiKeysModal";
import { McpModal } from "./components/McpModal";
import { DocumentsModal } from "./components/DocumentsModal";
import { AdminModal } from "./components/AdminModal";
import { Dashboard } from "./components/dashboard/Dashboard";
import { Compliance } from "./components/dashboard/Compliance";
import { useChat } from "./hooks/useChat";
import { useAuth } from "./context/AuthContext";
import type { RequestMode } from "./lib/types";

export default function App() {
  const { user, loading } = useAuth();

  const {
    conversations,
    active,
    activeId,
    streaming,
    send,
    stop,
    regenerate,
    newChat,
    selectChat,
    deleteChat,
  } = useChat();

  const [mode, setMode] = useState<RequestMode>("auto");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);
  const [mcpOpen, setMcpOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [view, setView] = useState<"chat" | "dashboard" | "compliance">("chat");

  if (loading) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Loader2 className="animate-spin text-ops-muted" />
      </div>
    );
  }

  if (!user) return <Login />;

  return (
    <div className="flex h-full w-full overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onNew={() => {
          setView("chat");
          newChat();
        }}
        onSelect={(id) => {
          setView("chat");
          selectChat(id);
          setSidebarOpen(false);
        }}
        onDelete={deleteChat}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpenKeys={() => setKeysOpen(true)}
        onOpenMcp={() => setMcpOpen(true)}
        onOpenDocs={() => setDocsOpen(true)}
        onOpenAdmin={() => setAdminOpen(true)}
        onOpenReports={() => setView("dashboard")}
        onOpenCompliance={() => setView("compliance")}
      />

      {view === "dashboard" ? (
        <Dashboard onBack={() => setView("chat")} />
      ) : view === "compliance" ? (
        <Compliance onBack={() => setView("chat")} />
      ) : (
        <div className="flex h-full min-w-0 flex-1 flex-col">
          <header className="glass flex h-12 items-center gap-2 border-b border-ops-border px-3">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded p-1.5 text-ops-muted hover:text-ops-text md:hidden"
            >
              <PanelLeft size={18} />
            </button>
            <span className="text-sm font-medium text-ops-text">
              {active?.title ?? "New chat"}
            </span>
            <span className="ml-auto rounded-full bg-ops-panel px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-ops-muted">
              {mode === "auto" ? "Auto-route" : mode.replace("ops-", "")}
            </span>
          </header>

          <main className="min-h-0 flex-1">
            <ChatWindow
              conversation={active}
              streaming={streaming}
              onRegenerate={() => regenerate(mode)}
              onPick={(text) => send(text, mode)}
            />
          </main>

          <Composer
            streaming={streaming}
            mode={mode}
            onModeChange={setMode}
            onSend={(text) => send(text, mode)}
            onStop={stop}
          />
        </div>
      )}

      {keysOpen && <ApiKeysModal onClose={() => setKeysOpen(false)} />}
      {mcpOpen && <McpModal onClose={() => setMcpOpen(false)} />}
      {docsOpen && <DocumentsModal onClose={() => setDocsOpen(false)} />}
      {adminOpen && <AdminModal onClose={() => setAdminOpen(false)} />}
    </div>
  );
}
