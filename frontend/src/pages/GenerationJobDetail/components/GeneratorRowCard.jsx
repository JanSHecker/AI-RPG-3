import React from "react";
import { ChevronRight, RotateCcw } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";
import { statusLabel } from "../../../shared/lib/format.js";
import { statusDotClass } from "../../../shared/lib/statusDot.js";
import {
  generatorCardTitle,
  generatorInstanceNote,
  isRetryableBatchStep,
} from "../generatorRows.js";

export default function GeneratorRowCard({
  row,
  collapsed,
  jobStatus,
  canRetrySteps,
  onToggle,
  onSelectInstance,
  onRetryStep,
}) {
  return (
    <article className="grid min-h-[86px] gap-[9px] border-b border-[#2e2e2c] px-3 py-2.5 pb-3 last:border-b-0">
      <button
        className="flex w-full min-w-0 cursor-pointer items-center justify-between gap-3 border-0 bg-transparent p-0 text-left text-inherit"
        type="button"
        onClick={() => onToggle(row.type)}
        aria-expanded={!collapsed}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <ChevronRight
            className={cx("text-[#aaa49a] transition-transform duration-150", !collapsed && "rotate-90")}
            size={16}
          />
          <span className="truncate text-[13px] font-semibold">{row.label}</span>
        </span>
        <span className="shrink-0 text-xs text-[#aaa49a]">{row.activeCount} active</span>
      </button>
      {!collapsed && row.instances.length > 0 ? (
        <div className="flex min-w-0 flex-wrap gap-2">
          {row.instances.map((instance) => {
            const title = generatorCardTitle(instance, row);
            const canRetryStep = Boolean(
              canRetrySteps &&
                jobStatus === "failed" &&
                instance.status === "failed" &&
                isRetryableBatchStep(instance.step_name),
            );
            return (
              <div
                key={instance.instanceId}
                className="w-full max-w-full overflow-hidden rounded-[7px] border border-[#35332f] bg-[#1d1d1b] p-0 text-left text-xs text-[#aaa49a] hover:bg-[#22221f] lg:w-[178px]"
              >
                <button
                  className="block w-full cursor-pointer border-0 bg-transparent px-2.5 py-[9px] text-left text-xs text-inherit focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#b98241]"
                  type="button"
                  onClick={() => onSelectInstance(instance.instanceId)}
                >
                  {title ? <div className="mb-[5px] truncate font-semibold text-[#eeeeec]">{title}</div> : null}
                  <div className="mb-[5px] flex min-w-0 items-center gap-2">
                    <span className={statusDotClass(instance.status)} aria-hidden="true" />
                    <span className="font-semibold text-[#eeeeec]">{statusLabel(instance.status)}</span>
                  </div>
                  <div>Attempts {instance.attempts}</div>
                  <div>{generatorInstanceNote(instance)}</div>
                  {instance.error ? <div className="mt-1 break-words leading-snug text-[#f0c6bd]">{instance.error}</div> : null}
                </button>
                {canRetryStep ? (
                  <button
                    className="flex min-h-[30px] w-full items-center justify-center gap-1.5 border-0 border-t border-[#35332f] bg-[#1a1a18] text-xs text-[#d7c4a7] hover:bg-[#22221f] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#b98241]"
                    type="button"
                    title="Retry batch"
                    onClick={() => onRetryStep(instance.step_name)}
                  >
                    <RotateCcw size={14} />
                    Retry
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </article>
  );
}
