import { api } from "@/lib/api-client";
import type { TaskInfo, GitImportRequest, DocImportRequest, MediaImportRequest, GraphBuildRequest, FinetuneGenRequest } from "@/types";
import { useMutation } from "@tanstack/react-query";

export function useImportGit() {
  return useMutation({
    mutationFn: (data: GitImportRequest) =>
      api.post<TaskInfo>("/import/git", data),
  });
}

export function useImportDocs() {
  return useMutation({
    mutationFn: (data: DocImportRequest) =>
      api.post<TaskInfo>("/import/docs", data),
  });
}

export function useImportMedia() {
  return useMutation({
    mutationFn: (data: MediaImportRequest) =>
      api.post<TaskInfo>("/import/media", data),
  });
}

export function useBuildGraph() {
  return useMutation({
    mutationFn: (data: GraphBuildRequest) =>
      api.post<TaskInfo>("/graph/build", data),
  });
}

export function useGenerateFinetune() {
  return useMutation({
    mutationFn: (data: FinetuneGenRequest) =>
      api.post<TaskInfo>("/finetune/generate", data),
  });
}
