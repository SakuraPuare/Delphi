import type { ProjectInfo, QueryRequest, SSEEvent } from "./types";

const BASE = "/api";

export async function fetchProjects(): Promise<ProjectInfo[]> {
  const res = await fetch(`${BASE}/projects`);
  if (!res.ok) throw new Error("Failed to fetch projects");
  return res.json();
}

export async function queryStream(
  req: QueryRequest,
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Query failed: ${text}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const json = trimmed.slice(6);
      try {
        const event: SSEEvent = JSON.parse(json);
        onEvent(event);
      } catch {
        // skip malformed lines
      }
    }
  }
}
