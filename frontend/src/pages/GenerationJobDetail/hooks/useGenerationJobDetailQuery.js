import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../../api/client.js";
import { queryKeys } from "../../../api/queryKeys.js";
import { POLL_INTERVAL_MS } from "../../../shared/lib/constants.js";

export function useGenerationJobQuery({ jobId, enabled }) {
  return useQuery({
    queryKey: queryKeys.generationJob(jobId),
    queryFn: async () => {
      const payload = await request(`/generation-jobs/${encodeURIComponent(jobId)}`);
      return payload.job ?? null;
    },
    enabled: enabled && !!jobId,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
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
    onSuccess: (payload, { jobId }) => {
      if (payload?.job) {
        qc.setQueryData(queryKeys.generationJob(jobId), payload.job);
      }
      qc.invalidateQueries({ queryKey: queryKeys.generationJobs });
      qc.invalidateQueries({ queryKey: queryKeys.worlds });
    },
  });
}

export function useRetryStepMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, stepName, modelId }) => {
      if (!jobId) throw new Error("Missing job id.");
      if (!stepName) throw new Error("Missing step name.");
      if (!modelId) throw new Error("Select a model before retrying this batch.");
      const params = new URLSearchParams({ model_id: modelId });
      return request(`/generation-jobs/${encodeURIComponent(jobId)}/steps/${encodeURIComponent(stepName)}/retry?${params.toString()}`, {
        method: "POST",
        body: JSON.stringify({ model_id: modelId }),
      });
    },
    onSuccess: (payload, { jobId }) => {
      if (payload?.job) {
        qc.setQueryData(queryKeys.generationJob(jobId), payload.job);
      }
      qc.invalidateQueries({ queryKey: queryKeys.generationJobs });
      qc.invalidateQueries({ queryKey: queryKeys.worlds });
    },
  });
}
