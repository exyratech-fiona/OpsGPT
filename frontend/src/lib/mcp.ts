import { authedFetch } from "./auth";

export interface McpTool {
  name: string;
  description: string;
}

export interface McpServer {
  id: string;
  name: string;
  provider_type: string;
  display_name: string;
  enabled: boolean;
  status: string; // untested | ok | error
  status_message: string | null;
  config: Record<string, unknown>;
  tools: McpTool[];
  created_at: string;
}

export interface TestResult {
  ok: boolean;
  message: string;
}

export async function fetchProviders(): Promise<McpServer[]> {
  const res = await authedFetch("/mcp/providers");
  if (!res.ok) return [];
  return (await res.json()) as McpServer[];
}

async function send(path: string, method: string, body?: unknown) {
  const res = await authedFetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as { detail?: string }).detail || `Error ${res.status}`);
  }
  return res.json().catch(() => ({}));
}

export function createServer(
  name: string,
  provider_type: string,
  config: Record<string, unknown>,
) {
  return send("/mcp/servers", "POST", { name, provider_type, config });
}

export function updateServer(
  id: string,
  body: { name?: string; enabled?: boolean; config?: Record<string, unknown> },
) {
  return send(`/mcp/servers/${id}`, "PATCH", body);
}

export function deleteServer(id: string) {
  return send(`/mcp/servers/${id}`, "DELETE");
}

export function testSaved(id: string): Promise<TestResult> {
  return send(`/mcp/servers/${id}/test`, "POST") as Promise<TestResult>;
}

export function testConfig(
  provider_type: string,
  config: Record<string, unknown>,
  server_id?: string,
): Promise<TestResult> {
  return send("/mcp/test", "POST", { provider_type, config, server_id }) as Promise<TestResult>;
}
