const DEFAULT_BACKEND =
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "/api";

export function backendUrl(path: string): string {
  if (DEFAULT_BACKEND.endsWith("/") && path.startsWith("/")) {
    return DEFAULT_BACKEND + path.slice(1);
  }
  return DEFAULT_BACKEND + path;
}

export interface ToolCall {
  substrate: string;
  tool: string;
  arguments: Record<string, unknown>;
  result_preview?: string;
  error?: string;
}

export interface ChatResponse {
  answer: string;
  tool_calls: ToolCall[];
}

export interface NvlNode {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
  caption: string;
}

export interface NvlRel {
  id: string;
  from: string;
  to: string;
  type: string;
  properties: Record<string, unknown>;
  caption: string;
}

export interface Subgraph {
  nodes: NvlNode[];
  relationships: NvlRel[];
}

export async function sendChat(message: string): Promise<ChatResponse> {
  const res = await fetch(backendUrl("/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    throw new Error(`Chat request failed: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

export async function fetchSubgraph(
  entityType: string,
  entityId: string,
  depth = 1
): Promise<Subgraph> {
  const params = new URLSearchParams({
    entity_type: entityType,
    entity_id: entityId,
    depth: String(depth),
  });
  const res = await fetch(backendUrl(`/subgraph?${params}`));
  if (!res.ok) {
    throw new Error(`Subgraph request failed: ${res.status}`);
  }
  return res.json();
}
