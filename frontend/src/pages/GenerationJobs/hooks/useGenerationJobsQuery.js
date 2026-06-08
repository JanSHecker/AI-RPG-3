import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../../api/client.js";
import { queryKeys } from "../../../api/queryKeys.js";
import { POLL_INTERVAL_MS } from "../../../shared/lib/constants.js";

export function useGenerationJobsQuery({ enabled }) {
  return useQuery({
    queryKey: queryKeys.generationJobs,
    queryFn: async () => {
      const payload = await request("/generation-jobs");
      return payload.jobs ?? [];
    },
    enabled,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useClearFinishedJobsMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => request("/generation-jobs/finished", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.generationJobs }),
  });
}

export function useClearActiveJobsMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => request("/generation-jobs/active", { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.generationJobs });
      qc.invalidateQueries({ queryKey: queryKeys.worlds });
    },
  });
}

export function useRestartJobMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, modelId }) => {
      if (!jobId) throw new Error("Missing job id.");
      if (!modelId) throw new Error("Select a model before restarting this job.");
      const params = new URLSearchParams({ model_id: modelId });
      return request(`/generation-jobs/${encodeURIComponent(jobId)}/restart?${params.toString()}`, {
        method: "POST",
        body: JSON.stringify({ model_id: modelId }),
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.generationJobs }),
  });
}
