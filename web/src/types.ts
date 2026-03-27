export interface Source {
  index: number;
  file: string;
  chunk: string;
  score: number;
  start_line: number | null;
  end_line: number | null;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

export interface ProjectInfo {
  name: string;
  description: string;
  chunk_count: number;
  created_at: string;
}

export interface QueryRequest {
  question: string;
  project: string;
  top_k: number;
  session_id: string | null;
}

export interface SSEToken {
  type: "token";
  content: string;
}

export interface SSESources {
  type: "sources";
  sources: Source[];
}

export interface SSEDone {
  type: "done";
  session_id: string | null;
}

export interface SSEError {
  type: "error";
  message: string;
}

export type SSEEvent = SSEToken | SSESources | SSEDone | SSEError;
