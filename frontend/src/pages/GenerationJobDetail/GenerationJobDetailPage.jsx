import React, { useState } from "react";
import { ArrowLeft, ExternalLink, Play, RefreshCw, RotateCcw } from "lucide-react";
import { cx } from "../../shared/lib/classNames.js";
import { formatDate, statusLabel } from "../../shared/lib/format.js";
import {
  button,
  buttonSecondary,
  emptyPanel,
  errorBanner,
  h1,
  headerActions,
  listPanel,
  muted,
} from "../../shared/ui/classes.js";
import {
  useGenerationJobQuery,
  useRestartJobMutation,
  useRetryStepMutation,
} from "./hooks/useGenerationJobDetailQuery.js";
import GeneratorRowCard from "./components/GeneratorRowCard.jsx";
import StepDetailDrawer from "./components/StepDetailDrawer.jsx";
import {
  generatorCardTitle,
  groupGeneratorInstances,
} from "./generatorRows.js";

export default function GenerationJobDetailPage({
  jobId,
  active,
  setError,
  error,
  activeModelId,
  onBack,
  onOpenWorld,
  onPlayWorld,
}) {
  const { data: job, isLoading, isError: isQueryError, error: queryError, refetch } = useGenerationJobQuery({ jobId, enabled: active });
  const restartMut = useRestartJobMutation();
  const retryStepMut = useRetryStepMutation();
  const [collapsedGeneratorRows, setCollapsedGeneratorRows] = useState({});
  const [selectedGeneratorId, setSelectedGeneratorId] = useState("");
  const generatorRows = groupGeneratorInstances(job?.steps ?? []);
  const selectedGenerator = generatorRows
    .flatMap((row) => row.instances.map((instance) => ({ instance, row })))
    .find(({ instance }) => instance.instanceId === selectedGeneratorId);
  const canOpen = job?.status === "done" && job?.world_id;
  const canRestart = job?.status === "failed";
  const toggleGeneratorRow = (rowType) => {
    setCollapsedGeneratorRows((current) => ({ ...current, [rowType]: !current[rowType] }));
  };

  const handleRestart = () => {
    setError("");
    restartMut.mutate(
      { jobId, modelId: activeModelId },
      { onError: (restartError) => setError(restartError.message) },
    );
  };

  const handleRetryStep = (stepName) => {
    setError("");
    retryStepMut.mutate(
      { jobId, stepName, modelId: activeModelId },
      { onError: (retryError) => setError(retryError.message) },
    );
  };

  const handleRefresh = () => {
    refetch().catch((loadError) => setError(loadError.message));
  };

  return (
    <main className="flex justify-center min-w-0 bg-[#111111] p-6">
      <div className="w-full max-w-[1040px]">
        <div className="mb-[18px] flex flex-wrap items-start justify-between gap-4 border-b border-[#2e2e2c] pb-3.5">
          <div className="min-w-0">
            <h1 className={h1}>Generation job</h1>
            <div className={muted}>
              {job ? `${statusLabel(job.status)} - ${job.provider}/${job.model_name}` : isLoading ? "Loading..." : "No job loaded"}
            </div>
            <div className="mt-1.5 truncate text-sm font-semibold text-[#eeeeec]">{job?.prompt ?? ""}</div>
            {job?.updated_at ? <div className={muted}>Updated {formatDate(job.updated_at)}</div> : null}
          </div>
          <div className={headerActions}>
            <button className={cx(button, buttonSecondary)} onClick={onBack}>
              <ArrowLeft size={16} />
              Back
            </button>
            {canOpen ? (
              <>
                <button className={cx(button, buttonSecondary)} onClick={() => onOpenWorld(job.world_id)}>
                  <ExternalLink size={16} />
                  Open
                </button>
                <button className={cx(button, buttonSecondary)} onClick={() => onPlayWorld(job.world_id)}>
                  <Play size={16} />
                  Play
                </button>
              </>
            ) : null}
            {canRestart ? (
              <button
                className={cx(button, buttonSecondary)}
                onClick={handleRestart}
              >
                <RotateCcw size={16} />
                Restart
              </button>
            ) : null}
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
        {isQueryError && queryError ? <div className={errorBanner}>{queryError.message}</div> : null}
        {job?.error ? <div className={errorBanner}>{job.error}</div> : null}

        <section className={listPanel}>
          {isLoading && !job ? (
            <div className={emptyPanel}>Loading generation job.</div>
          ) : generatorRows.length === 0 ? (
            <div className={emptyPanel}>No generator instances recorded.</div>
          ) : (
            generatorRows.map((row) => (
              <GeneratorRowCard
                key={row.type}
                row={row}
                collapsed={Boolean(collapsedGeneratorRows[row.type])}
                jobStatus={job?.status}
                canRetrySteps={Boolean(activeModelId)}
                onToggle={toggleGeneratorRow}
                onSelectInstance={setSelectedGeneratorId}
                onRetryStep={handleRetryStep}
              />
            ))
          )}
        </section>
        <StepDetailDrawer
          instance={selectedGenerator?.instance ?? null}
          title={selectedGenerator ? generatorCardTitle(selectedGenerator.instance, selectedGenerator.row) || selectedGenerator.row.label : ""}
          onClose={() => setSelectedGeneratorId("")}
        />
      </div>
    </main>
  );
}
