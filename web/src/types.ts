export interface Source {
  index: number;
  file: string;
  chunk: string;
  score: number;
  start_line?: number;
  end_line?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  timestamp: number;
  streaming?: boolean;
}

export interface ProjectInfo {
  name: string;
  description?: string;
  chunk_count: number;
  created_at?: string;
}

export interface ServiceStatus {
  ok: boolean;
  model?: string;
  collections?: number;
  error?: string;
}

export interface SystemStatus {
  vllm: ServiceStatus;
  qdrant: ServiceStatus;
  embedding: ServiceStatus;
}

export interface AgentStep {
  thought: string;
  action?: string;
  observation?: string;
  answer?: string;
}

export interface Conversation {
  id: string;
  title: string;
  project: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

// SSE event types
export type SSEEvent =
  | { type: "token"; content: string }
  | { type: "sources"; sources: Source[] }
  | { type: "done"; session_id: string }
  | { type: "error"; message: string }
  | { type: "thought"; content: string }
  | { type: "action"; tool: string; args: string }
  | { type: "observation"; content: string };

// Task progress (WebSocket)
export type TaskStatus = "pending" | "running" | "done" | "failed";

export interface TaskProgress {
  event: "snapshot" | "created" | "progress" | "completed" | "failed";
  task_id: string;
  task_type: string;
  status: TaskStatus;
  progress: number;
  message: string;
  metadata: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at: number;
  updated_at: number;
}
