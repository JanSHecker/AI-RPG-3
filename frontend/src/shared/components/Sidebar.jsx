import React, { useEffect, useState } from "react";
import { Check, ListChecks, Plus, RefreshCw } from "lucide-react";
import { cx } from "../lib/classNames.js";
import { formatDate } from "../lib/format.js";
import { useTestModelMutation } from "../../app/hooks/useModelsQuery.js";
import {
  button,
  buttonPrimary,
  buttonSecondary,
  emptyPanel,
  iconButton,
  label,
  select,
} from "../ui/classes.js";

const modelTextOk = "text-[#b6d2b9]";
const modelTextTesting = "text-[#d7c4a7]";
const modelTextFailed = "text-[#f0c6bd]";
const modelTextDefault = "text-[#c9c2b8]";

function modelStatusClass(status) {
  return {
    testing: modelTextTesting,
    ok: modelTextOk,
    failed: modelTextFailed,
  }[status] ?? modelTextDefault;
}

export default function Sidebar({
  worlds,
  selectedWorldId,
  onSelectWorld,
  onNewWorld,
  onShowJobs,
  onRefresh,
  models,
  activeModelId,
  onSelectModel,
}) {
  const [modelStatus, setModelStatus] = useState("idle");
  const [modelTestResult, setModelTestResult] = useState(null);
  const testMutation = useTestModelMutation();

  useEffect(() => {
    setModelStatus("idle");
    setModelTestResult(null);
  }, [activeModelId]);

  const activeModel = models.find((model) => model.id === activeModelId);
  const isTesting = testMutation.isPending;

  const handleTestModel = () => {
    if (!activeModel || isTesting) return;
    setModelStatus("testing");
    setModelTestResult(null);
    testMutation.mutate(activeModel, {
      onSuccess: (payload) => {
        const result = payload.results?.[0];
        if (!result) {
          setModelStatus("failed");
          setModelTestResult({ error: "Model test returned no result." });
          return;
        }
        setModelStatus(result.ok ? "ok" : "failed");
        setModelTestResult({
          latency_ms: result.latency_ms,
          response_preview: result.response_preview,
          error: result.error || (result.ok ? "" : "Model test failed."),
        });
      },
      onError: (testError) => {
        setModelStatus("failed");
        setModelTestResult({ error: testError.message });
      },
    });
  };

  const modelStatusText = {
    idle: "Waiting to test selected model.",
    testing: "Waiting for the model response...",
    ok: `Model responded successfully${modelTestResult?.latency_ms != null ? ` in ${modelTestResult.latency_ms} ms` : ""}.`,
    failed: "Model test failed.",
  }[modelStatus] ?? "Waiting to test selected model.";
  const modelError = modelStatus === "failed" ? modelTestResult?.error : "";
  const modelPreview = modelStatus === "ok" ? modelTestResult?.response_preview : "";

  return (
    <aside className="flex min-h-[auto] flex-col border-b border-[#2e2e2c] bg-[#171716] lg:min-h-screen lg:border-r lg:border-b-0">
      <div className="border-b border-[#2e2e2c] px-[18px] pt-[18px] pb-4">
        <div className="text-[17px] font-semibold">World Data</div>
        <div className="mt-[3px] text-[13px] text-[#aaa49a]">Text RPG generator</div>
      </div>

      <div className="flex gap-2 border-b border-[#2e2e2c] p-3.5">
        <button className={cx(button, buttonPrimary)} onClick={onNewWorld}>
          <Plus size={16} />
          New world
        </button>
        <button className={iconButton} onClick={onShowJobs} title="Generation jobs">
          <ListChecks size={16} />
        </button>
        <button className={iconButton} onClick={onRefresh} title="Refresh worlds">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="grid gap-2 border-b border-[#2e2e2c] p-3.5">
        <label className={label} htmlFor="model-select">Model</label>
        <select className={select} id="model-select" value={activeModelId || ""} onChange={(event) => onSelectModel(event.target.value)}>
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.label}
            </option>
          ))}
        </select>
        <button className={cx(button, buttonSecondary, "w-full")} onClick={handleTestModel} disabled={!activeModelId || isTesting}>
          {isTesting ? <RefreshCw size={16} /> : <Check size={16} />}
          {isTesting ? "Testing" : "Test model"}
        </button>
        <div className="min-h-[52px] rounded-[7px] border border-[#2e2e2c] bg-[#151514] px-2.5 py-[9px] text-xs leading-[1.45] text-[#aaa49a]" aria-live="polite">
          <div className={modelStatusClass(modelStatus)}>{modelStatusText}</div>
          {modelError ? <div className={cx("mt-[5px] break-words text-[#aaa49a]", modelTextFailed)}>{modelError}</div> : null}
          {modelPreview ? <div className="mt-[5px] break-words text-[#aaa49a]">Response: {modelPreview}</div> : null}
        </div>
      </div>

      <div className="grid max-h-[220px] min-h-0 grid-cols-[repeat(auto-fill,minmax(210px,1fr))] overflow-auto p-2 lg:block lg:max-h-none">
        {worlds.length === 0 ? (
          <div className={emptyPanel}>No worlds yet.</div>
        ) : (
          worlds.map((world) => (
            <button
              key={world.id}
              className={cx(
                "grid w-full gap-[3px] rounded-[7px] border border-transparent p-2.5 text-left text-inherit hover:border-[#3a3834] hover:bg-[#20201e]",
                selectedWorldId === world.id && "border-[#3a3834] bg-[#20201e]",
              )}
              onClick={() => onSelectWorld(world.id)}
            >
              <span className="truncate text-sm font-semibold">{world.title}</span>
              <span className="truncate text-xs text-[#aaa49a]">{world.provider} - {formatDate(world.updated_at)}</span>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
