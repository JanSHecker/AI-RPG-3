import { useCallback, useEffect, useState } from "react";
import { request } from "../../../api/client.js";

export function useGenerationJobDetailPage({ jobId, active, setError, onWorldsChanged, activeModelId }) {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadGenerationJob = useCallback(async (targetJobId = jobId) => {
    if (!targetJobId) return null;
    setJob(null);
    setLoading(true);
    try {
      const payload = await request(`/generation-jobs/${encodeURIComponent(targetJobId)}`);
      setJob(payload.job ?? null);
      return payload.job ?? null;
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    if (!active || !jobId) return undefined;
    let cancelled = false;
    const pollJob = async () => {
      try {
        const payload = await request(`/generation-jobs/${encodeURIComponent(jobId)}`);
        if (!cancelled) {
          setJob(payload.job ?? null);
          if (onWorldsChanged) onWorldsChanged();
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError.message);
      }
    };
    pollJob();
    const intervalId = window.setInterval(pollJob, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [active, jobId, setError, onWorldsChanged]);

  const restartGenerationJob = async () => {
    if (!jobId) return;
    if (!activeModelId) {
      throw new Error("Select a model before restarting this job.");
    }
    setError("");
    const params = new URLSearchParams({ model_id: activeModelId });
    const payload = await request(`/generation-jobs/${encodeURIComponent(jobId)}/restart?${params.toString()}`, {
      method: "POST",
      body: JSON.stringify({ model_id: activeModelId }),
    });
    setJob(payload.job ?? null);
    if (onWorldsChanged) await onWorldsChanged();
  };

  const retryGenerationJobStep = async (stepName) => {
    if (!jobId || !stepName) return;
    if (!activeModelId) {
      throw new Error("Select a model before retrying this batch.");
    }
    setError("");
    const params = new URLSearchParams({ model_id: activeModelId });
    const payload = await request(`/generation-jobs/${encodeURIComponent(jobId)}/steps/${encodeURIComponent(stepName)}/retry?${params.toString()}`, {
      method: "POST",
      body: JSON.stringify({ model_id: activeModelId }),
    });
    setJob(payload.job ?? null);
    if (onWorldsChanged) await onWorldsChanged();
  };

  return {
    job,
    loading,
    loadGenerationJob,
    restartGenerationJob,
    retryGenerationJobStep,
  };
}
