import React from "react";
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
import { useGenerationJobsPage } from "./hooks/useGenerationJobsPage.js";
import GenerationJobRow from "./components/GenerationJobRow.jsx";

export default function GenerationJobsPage({
  active,
  setError,
  error,
  activeModelId,
  onWorldsChanged,
  onSelectJob,
  onOpenWorld,
  onPlayWorld,
}) {
  const {
    jobs,
    loading,
    loadGenerationJobs,
    clearFinishedJobs,
    clearActiveJobs,
    restartGenerationJob,
  } = useGenerationJobsPage({ active, setError, onWorldsChanged, activeModelId });

  const activeCount = jobs.filter((job) => ["pending", "running", "retrying"].includes(job.status)).length;
  const finishedCount = jobs.filter((job) => ["done", "failed"].includes(job.status)).length;

  return (
    <main className="flex justify-center min-w-0 bg-[#111111] p-6">
      <div className="w-full max-w-[1040px]">
        <div className="mb-[18px] flex items-start justify-between gap-4">
          <div>
            <h1 className={h1}>Generation jobs</h1>
            <div className={muted}>{loading ? "Refreshing..." : `${jobs.length} visible`}</div>
          </div>
          <div className={headerActions}>
            <button
              className={cx(button, buttonSecondary)}
              onClick={() => clearFinishedJobs().catch((clearError) => setError(clearError.message))}
              disabled={finishedCount === 0}
            >
              <Trash2 size={16} />
              Clear old
            </button>
            <button
              className={cx(button, buttonDanger)}
              onClick={() => clearActiveJobs().catch((clearError) => setError(clearError.message))}
              disabled={activeCount === 0}
            >
              <Trash2 size={16} />
              Clear running
            </button>
            <button
              className={cx(button, buttonSecondary)}
              onClick={() => loadGenerationJobs().catch((loadError) => setError(loadError.message))}
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
                onRestartJob={(jobId) => restartGenerationJob(jobId).catch((restartError) => setError(restartError.message))}
              />
            ))
          )}
        </section>
      </div>
    </main>
  );
}
