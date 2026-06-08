import { useCallback, useEffect, useState } from "react";
import { request } from "../../../api/client.js";

export function useGenerationJobsPage({ active, setError, onWorldsChanged, activeModelId }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadGenerationJobs = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await request("/generation-jobs");
      setJobs(payload.jobs ?? []);
      return payload.jobs ?? [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const pollJobs = async () => {
      try {
        const payload = await request("/generation-jobs");
        if (!cancelled) {
          setJobs(payload.jobs ?? []);
          if (onWorldsChanged) onWorldsChanged();
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError.message);
      }
    };
    pollJobs();
    const intervalId = window.setInterval(pollJobs, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [active, setError, onWorldsChanged]);

  const clearFinishedJobs = async () => {
    const confirmed = window.confirm("Clear finished and failed generation jobs?");
    if (!confirmed) return;
    const payload = await request("/generation-jobs/finished", { method: "DELETE" });
    setJobs(payload.jobs ?? []);
  };

  const clearActiveJobs = async () => {
    const confirmed = window.confirm("Clear pending and running generation jobs? Running generation will be stopped.");
    if (!confirmed) return;
    const payload = await request("/generation-jobs/active", { method: "DELETE" });
    setJobs(payload.jobs ?? []);
    if (onWorldsChanged) await onWorldsChanged();
  };

  const restartGenerationJob = async (jobId) => {
    if (!jobId) return;
    if (!activeModelId) {
      throw new Error("Select a model before restarting this job.");
    }
    setError("");
    const params = new URLSearchParams({ model_id: activeModelId });
    await request(`/generation-jobs/${encodeURIComponent(jobId)}/restart?${params.toString()}`, {
      method: "POST",
      body: JSON.stringify({ model_id: activeModelId }),
    });
    await loadGenerationJobs();
  };

  return {
    jobs,
    loading,
    loadGenerationJobs,
    clearFinishedJobs,
    clearActiveJobs,
    restartGenerationJob,
  };
}
