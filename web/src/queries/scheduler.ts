import { api } from "@/lib/api-client";
import type { SchedulerJob } from "@/types";
import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

export const schedulerQueryOptions = queryOptions({
  queryKey: ["scheduler"],
  queryFn: () => api.get<SchedulerJob[]>("/scheduler/jobs"),
});

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<SchedulerJob>) =>
      api.post<SchedulerJob>("/scheduler/jobs", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler"] }),
  });
}

export function useDeleteJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/scheduler/jobs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler"] }),
  });
}

export function useToggleJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.put(`/scheduler/jobs/${id}`, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scheduler"] }),
  });
}
