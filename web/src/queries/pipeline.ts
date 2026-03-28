import { api } from "@/lib/api-client";
import { queryOptions } from "@tanstack/react-query";

// --- Types ---

export interface ChunkDetail {
  id: string;
  text_preview: string;
  file_path: string;
  language: string;
  node_type: string;
  symbol_name: string;
  parent_symbol: string;
  start_line: number;
  end_line: number;
}

export interface ChunkListResponse {
  chunks: ChunkDetail[];
  next_offset: string | null;
  total: number;
}

export interface ProjectStats {
  total_chunks: number;
  by_language: Record<string, number>;
  by_node_type: Record<string, number>;
  top_files: Array<{ file_path: string; count: number }>;
}

export interface DebugSource {
  file: string;
  chunk: string;
  start_line: number | null;
  end_line: number | null;
  vector_score: number;
  rerank_score: number | null;
  from_graph: boolean;
  node_type: string;
  language: string;
}

export interface QueryDebugResponse {
  answer: string;
  rewritten_query: string | null;
  intent: string;
  vector_results: DebugSource[];
  reranked_results: DebugSource[];
  final_results: DebugSource[];
  timings: Record<string, number>;
  session_id: string | null;
}

// --- Queries ---

export function projectStatsOptions(name: string) {
  return queryOptions({
    queryKey: ["project-stats", name],
    queryFn: () => api.get<ProjectStats>(`/projects/${name}/stats`),
    enabled: !!name,
  });
}

export function projectChunksOptions(
  name: string,
  params?: { limit?: number; offset?: string; language?: string; node_type?: string; file_path?: string },
) {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", params.offset);
  if (params?.language) searchParams.set("language", params.language);
  if (params?.node_type) searchParams.set("node_type", params.node_type);
  if (params?.file_path) searchParams.set("file_path", params.file_path);
  const qs = searchParams.toString();
  return queryOptions({
    queryKey: ["project-chunks", name, params],
    queryFn: () => api.get<ChunkListResponse>(`/projects/${name}/chunks${qs ? `?${qs}` : ""}`),
    enabled: !!name,
  });
}

export async function queryDebug(
  question: string,
  project: string,
  options?: { top_k?: number; use_graph_rag?: boolean },
): Promise<QueryDebugResponse> {
  return api.post<QueryDebugResponse>("/query/debug", {
    question,
    project,
    top_k: options?.top_k ?? 5,
    use_graph_rag: options?.use_graph_rag ?? true,
  });
}
