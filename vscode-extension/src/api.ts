import * as vscode from "vscode";

export interface Source {
  file: string;
  start_line?: number;
  end_line?: number;
  score: number;
  chunk?: string;
}

export interface StreamEvent {
  type: "token" | "sources" | "done" | "error";
  content?: string;
  sources?: Source[];
  session_id?: string;
  message?: string;
}

function getConfig() {
  const cfg = vscode.workspace.getConfiguration("delphi");
  return {
    apiUrl: cfg.get<string>("apiUrl", "http://localhost:8888"),
    project: cfg.get<string>("project", ""),
    topK: cfg.get<number>("topK", 5),
  };
}

export async function* queryStream(
  question: string,
  sessionId?: string
): AsyncGenerator<StreamEvent> {
  const { apiUrl, project, topK } = getConfig();

  const resp = await fetch(`${apiUrl}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      project,
      top_k: topK,
      session_id: sessionId ?? null,
    }),
  });

  if (!resp.ok) {
    yield { type: "error", message: `HTTP ${resp.status}: ${resp.statusText}` };
    return;
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    yield { type: "error", message: "No response body" };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) {
        continue;
      }
      const json = trimmed.slice(6);
      if (json === "[DONE]") {
        return;
      }
      try {
        yield JSON.parse(json) as StreamEvent;
      } catch {
        // skip malformed lines
      }
    }
  }
}

export interface ProjectInfo {
  name: string;
  chunk_count: number;
}

export async function fetchProjects(): Promise<ProjectInfo[]> {
  const { apiUrl } = getConfig();
  const resp = await fetch(`${apiUrl}/projects`);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  return resp.json() as Promise<ProjectInfo[]>;
}
