import React, { useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";
import { cx } from "../../shared/lib/classNames.js";
import {
  button,
  buttonDanger,
  buttonSecondary,
  emptyPanel,
  errorBanner,
  h1,
  headerActions,
  listPanel,
  muted,
} from "../../shared/ui/classes.js";
import {
  useGenerationJobsQuery,
  useClearFinishedJobsMutation,
  useClearActiveJobsMutation,
  useRestartJobMutation,
} from "./hooks/useGenerationJobsQuery.js";
import GenerationJobRow from "./components/GenerationJobRow.jsx";

export default function GenerationJobsPage({
  active,
  setError,
  error,
  activeModelId,
  onSelectJob,
  onOpenWorld,
  onPlayWorld,
}) {
  const { data: jobs = [], refetch } = useGenerationJobsQuery({ enabled: active });
  const clearFinishedMut = useClearFinishedJobsMutation();
  const clearActiveMut = useClearActiveJobsMutation();
  const restartMut = useRestartJobMutation();
  const [isManualRefetching, setIsManualRefetching] = useState(false);

  const activeCount = jobs.filter((job) => ["pending", "running", "retrying"].includes(job.status)).length;
  const finishedCount = jobs.filter((job) => ["done", "failed"].includes(job.status)).length;

  const handleClearFinished = async () => {
    if (!window.confirm("Clear finished and failed generation jobs?")) return;
    try {
      await clearFinishedMut.mutateAsync();
    } catch (clearError) {
      setError(clearError.message);
    }
  };

  const handleClearActive = async () => {
    if (!window.confirm("Clear pending and running generation jobs? Running generation will be stopped.")) return;
    try {
      await clearActiveMut.mutateAsync();
    } catch (clearError) {
      setError(clearError.message);
    }
  };

  const handleRefresh = () => {
    setIsManualRefetching(true);
    refetch()
      .catch((loadError) => setError(loadError.message))
      .finally(() => setIsManualRefetching(false));
  };

  const handleRestart = (jobId) => {
    setError("");
    restartMut.mutate(
      { jobId, modelId: activeModelId },
      { onError: (restartError) => setError(restartError.message) },
    );
  };

  return (
    <main className="flex justify-center min-w-0 bg-[#111111] p-6">
      <div className="w-full max-w-[1040px]">
        <div className="mb-[18px] flex items-start justify-between gap-4">
          <div>
            <h1 className={h1}>Generation jobs</h1>
            <div className={muted}>{isManualRefetching ? "Refreshing..." : `${jobs.length} visible`}</div>
          </div>
          <div className={headerActions}>
            <button
              className={cx(button, buttonSecondary)}
              onClick={handleClearFinished}
              disabled={finishedCount === 0}
            >
              <Trash2 size={16} />
              Clear old
            </button>
            <button
              className={cx(button, buttonDanger)}
              onClick={handleClearActive}
              disabled={activeCount === 0}
            >
              <Trash2 size={16} />
              Clear running
            </button>
            <button
              className={cx(button, buttonSecondary)}
              onClick={handleRefresh}
            >
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>
        </div>

        {error ? <div className={errorBanner}>{error}</div> : null}

        <section className={listPanel}>
          {jobs.length === 0 ? (
            <div className={emptyPanel}>No generation jobs.</div>
          ) : (
            jobs.map((job) => (
              <GenerationJobRow
                key={job.id}
                job={job}
                onSelect={onSelectJob}
                onOpenWorld={onOpenWorld}
                onPlayWorld={onPlayWorld}
                onRestartJob={handleRestart}
              />
            ))
          )}
        </section>
      </div>
    </main>
  );
}
