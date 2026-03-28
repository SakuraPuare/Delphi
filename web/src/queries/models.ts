import { api } from "@/lib/api-client";
import type { ModelInfo } from "@/types";
import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

export const modelsQueryOptions = queryOptions({
  queryKey: ["models"],
  queryFn: () => api.get<ModelInfo[]>("/models"),
});

export function useRegisterModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      name: string;
      model_path: string;
      model_type?: string;
      base_model?: string;
      description?: string;
    }) => api.post<ModelInfo>("/models", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useActivateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.post(`/models/activate`, { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}
