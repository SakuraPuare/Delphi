import type { ProjectInfo, SystemStatus, SSEEvent } from "@/types";

const API_BASE = "/api";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

export async function fetchProjects(): Promise<ProjectInfo[]> {
  return fetchJSON("/projects");
}

export async function fetchStatus(): Promise<SystemStatus> {
  return fetchJSON("/status");
}

export async function createProject(name: string, description = ""): Promise<ProjectInfo> {
  return fetchJSON("/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export async function deleteProject(name: string): Promise<void> {
  await fetch(`${API_BASE}/projects/${name}`, { method: "DELETE" });
}

export async function* queryStream(
  question: string,
  project: string,
  topK: number = 5,
  sessionId?: string | null,
): AsyncGenerator<SSEEvent> {
  const resp = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      project,
      top_k: topK,
      session_id: sessionId ?? null,
    }),
  });

  if (!resp.ok || !resp.body) {
    throw new Error("Stream request failed");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (!data || data === "[DONE]") continue;
      try {
        yield JSON.parse(data) as SSEEvent;
      } catch {
        // skip malformed JSON
      }
    }
  }
}

export async function* agentQueryStream(
  question: string,
  project: string,
  maxSteps: number = 5,
  sessionId?: string | null,
): AsyncGenerator<SSEEvent> {
  const resp = await fetch(`${API_BASE}/agent/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      project,
      max_steps: maxSteps,
      session_id: sessionId ?? null,
    }),
  });

  if (!resp.ok || !resp.body) {
    throw new Error("Agent stream request failed");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (!data || data === "[DONE]") continue;
      try {
        yield JSON.parse(data) as SSEEvent;
      } catch {
        // skip malformed JSON
      }
    }
  }
}
