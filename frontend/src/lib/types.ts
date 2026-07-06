export type Role = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  /** assistant-only: the model's <think> phase (Ops Think mode) */
  reasoning?: string;
  /** assistant-only: tool calls made during this turn (Ops Cluster mode) */
  toolSteps?: ToolStep[];
  /** assistant-only: document sources used (Ops Docs / RAG mode) */
  citations?: Citation[];
  /** assistant-only: generation stats (token count + tokens/sec) */
  stats?: { tokens: number; tps: number };
  /** assistant-only: which mode/model produced this turn */
  mode?: string;
  model?: string;
  error?: boolean;
}

export interface ToolStep {
  name: string;
  arguments?: Record<string, unknown>;
  result?: string;
}

export interface Citation {
  index: number;
  filename: string;
  page: number | null;
  score: number;
}

export interface McpTool {
  name: string;
  description: string;
}

export interface McpProvider {
  name: string;
  display_name: string;
  description: string;
  connected: boolean;
  tools: McpTool[];
}

export interface AdminStats {
  users: number;
  documents: number;
  chats: number;
  tokens: number;
  tool_calls: number;
  models: Record<string, boolean>;
  embed: boolean;
  system: {
    cpu_percent: number;
    cpu_count: number;
    mem_total: number;
    mem_used: number;
    mem_percent: number;
    load_avg: number[];
  };
}

export interface AdminUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  daily_token_limit: number;
  tokens_used_today: number;
  tokens_used_total: number;
  usage_date: string | null;
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  error: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

export type RequestMode =
  | "auto"
  | "ops-chat"
  | "ops-think"
  | "ops-code"
  | "ops-docs"
  | "ops-cluster";

export interface ModeInfo {
  id: string;
  display_name: string;
  model: string;
  description: string;
}

/** Discriminated union of the SSE events emitted by the backend. */
export type StreamEvent =
  | { type: "meta"; mode: string; model: string; display_name: string; tools?: boolean }
  | { type: "reasoning"; content: string }
  | { type: "tool_call"; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: string }
  | { type: "citations"; items: Citation[] }
  | { type: "stats"; tokens: number; tps: number }
  | { type: "token"; content: string }
  | { type: "error"; message: string }
  | { type: "done" };
