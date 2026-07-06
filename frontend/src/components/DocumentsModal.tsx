import { useEffect, useRef, useState } from "react";
import { FileText, Loader2, Trash2, Upload, X } from "lucide-react";
import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "../lib/docs";
import type { DocumentInfo } from "../lib/types";

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DocumentsModal({ onClose }: { onClose: () => void }) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setDocs(await listDocuments());
    setLoading(false);
  };

  useEffect(() => {
    refresh();
  }, []);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDocument(file);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const onDelete = async (id: string) => {
    await deleteDocument(id);
    await refresh();
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
            <FileText size={16} className="text-ops-accent" />
            <h2 className="text-sm font-semibold">Documents (RAG)</h2>
          </div>
          <button onClick={onClose} className="text-ops-muted hover:text-ops-text">
            <X size={18} />
          </button>
        </div>

        <div className="p-5">
          <p className="mb-3 text-xs text-ops-muted">
            Upload PDFs or text files, then ask questions in <b>Docs</b> mode —
            answers cite the source pages. Each document is private to your account.
          </p>

          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md,.markdown,.log,.yaml,.yml,.json,.csv"
            className="hidden"
            onChange={onFile}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="mb-4 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-ops-border bg-ops-panel/50 py-3 text-sm text-ops-muted transition hover:border-ops-accent/50 hover:text-ops-text disabled:opacity-50"
          >
            {uploading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Upload size={15} />
            )}
            {uploading ? "Indexing…" : "Upload a document"}
          </button>

          {error && (
            <div className="mb-3 rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}

          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {loading ? (
              <div className="py-6 text-center text-ops-muted">
                <Loader2 size={18} className="mx-auto animate-spin" />
              </div>
            ) : docs.length === 0 ? (
              <p className="py-6 text-center text-xs text-ops-muted">
                No documents yet
              </p>
            ) : (
              docs.map((d) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between rounded-lg border border-ops-border bg-ops-panel px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium" title={d.filename}>
                      {d.filename}
                    </div>
                    <div className="text-[11px] text-ops-muted">
                      {fmtSize(d.size_bytes)} · {d.chunk_count} chunks ·{" "}
                      <span
                        className={
                          d.status === "ready"
                            ? "text-ops-accent"
                            : d.status === "failed"
                              ? "text-red-400"
                              : "text-ops-muted"
                        }
                      >
                        {d.status}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => onDelete(d.id)}
                    title="Delete"
                    className="text-ops-muted hover:text-red-400"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
