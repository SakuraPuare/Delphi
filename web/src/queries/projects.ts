import { api } from "@/lib/api-client";
import type { ProjectInfo } from "@/types";
import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

export const projectsQueryOptions = queryOptions({
  queryKey: ["projects"],
  queryFn: () => api.get<ProjectInfo[]>("/projects"),
});

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      api.post<ProjectInfo>("/projects", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.delete(`/projects/${name}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}
