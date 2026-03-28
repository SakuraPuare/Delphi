import { api } from "@/lib/api-client";
import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

export interface SettingsGroup {
  [key: string]: Record<string, unknown>;
  llm: { vllm_url: string; llm_model: string; llm_api_key: string; llm_no_think: boolean };
  embedding: { embedding_url: string; embedding_model: string; embedding_api_key: string; embedding_backend: string };
  reranker: { reranker_url: string; reranker_model: string; reranker_enabled: boolean; reranker_top_k: number; reranker_score_threshold: number };
  rag: { chunk_top_k: number; query_rewrite_enabled: boolean; retrieve_top_k: number };
  server: { host: string; port: number; debug: boolean; api_key: string };
  otel: { otel_enabled: boolean; otel_endpoint: string; otel_service_name: string };
}

export const settingsQueryOptions = queryOptions({
  queryKey: ["settings"],
  queryFn: () => api.get<SettingsGroup>("/settings"),
});

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.put<SettingsGroup>("/settings", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}
