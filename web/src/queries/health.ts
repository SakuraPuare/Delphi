import { api } from "@/lib/api-client";
import type { SystemStatus } from "@/types";
import { queryOptions } from "@tanstack/react-query";

export const healthQueryOptions = queryOptions({
  queryKey: ["health"],
  queryFn: () => api.get<SystemStatus>("/status"),
  refetchInterval: 30_000,
});
