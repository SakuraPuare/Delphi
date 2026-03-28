// Shared types for the Delphi frontend

// --- API Response Types ---

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

export interface ProjectInfo {
  name: string;
  description: string;
  chunk_count: number;
  created_at: string;
}

export interface Source {
  index: number;
  file: string;
  chunk: string;
  score: number;
  start_line?: number;
  end_line?: number;
}

export interface TaskInfo {
  task_id: string;
  task_type?: string;
  status: "pending" | "running" | "done" | "failed";
  progress: number;
  total: number;
  processed: number;
  message?: string;
  metadata?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string;
  created_at?: number;
  updated_at?: number;
}

// --- Request Types ---

export interface GitImportRequest {
  url: string;
  project: string;
  branch?: string;
  include?: string[];
  exclude?: string[];
  depth?: number;
}

export interface DocImportRequest {
  path: string;
  project: string;
  recursive?: boolean;
  file_types?: string[];
}

export interface MediaImportRequest {
  path: string;
  project: string;
  recursive?: boolean;
  whisper_model?: string;
}

export interface QueryRequest {
  question: string;
  project?: string;
  top_k?: number;
  session_id?: string | null;
  use_graph_rag?: boolean;
}

export interface AgentQueryRequest {
  question: string;
  project?: string;
  max_steps?: number;
  session_id?: string | null;
}

export interface GraphBuildRequest {
  project: string;
  path: string;
  include?: string[];
  exclude?: string[];
}

export interface FinetuneGenRequest {
  project: string;
  num_samples?: number;
  questions_per_chunk?: number;
  format?: string;
  output_path?: string;
}

// --- SSE Event Types ---

export type SSEEventType =
  | "token"
  | "sources"
  | "done"
  | "error"
  | "thought"
  | "action"
  | "observation";

export interface TokenEvent {
  type: "token";
  content: string;
}

export interface SourcesEvent {
  type: "sources";
  sources: Source[];
}

export interface DoneEvent {
  type: "done";
  session_id?: string;
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

export interface ThoughtEvent {
  type: "thought";
  content: string;
}

export interface ActionEvent {
  type: "action";
  content: string;
}

export interface ObservationEvent {
  type: "observation";
  content: string;
}

export type StreamEvent =
  | TokenEvent
  | SourcesEvent
  | DoneEvent
  | ErrorEvent
  | ThoughtEvent
  | ActionEvent
  | ObservationEvent;

// --- WebSocket Task Events ---

export type TaskWSEvent = "snapshot" | "created" | "progress" | "completed" | "failed";

export interface TaskProgress {
  event: TaskWSEvent;
  task_id: string;
  task_type: string;
  status: "pending" | "running" | "done" | "failed";
  progress: number;
  message: string;
  metadata: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at: number;
  updated_at: number;
}

// --- UI Types ---

export interface AgentStep {
  thought: string;
  action?: string;
  observation?: string;
  answer?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  agentSteps?: AgentStep[];
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  project: string;
  sessionId: string | null;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

// --- Model Types ---

export interface ModelInfo {
  name: string;
  model_path: string;
  model_type: string;
  base_model: string;
  description: string;
  active: boolean;
}

export interface SchedulerJob {
  id: string;
  name: string;
  cron: string;
  task_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  last_run?: string;
  next_run?: string;
}

export interface SymbolInfo {
  name: string;
  qualified_name: string;
  kind: string;
  file_path: string;
  start_line: number;
  end_line: number;
  language: string;
}

export interface RelationInfo {
  source: string;
  target: string;
  kind: string;
}
