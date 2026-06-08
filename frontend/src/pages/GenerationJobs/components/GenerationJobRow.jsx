import React from "react";
import { ChevronRight, ExternalLink, Play, RotateCcw } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";
import { formatDate, statusLabel } from "../../../shared/lib/format.js";
import { statusDotClass } from "../../../shared/lib/statusDot.js";
import { button, buttonSecondary } from "../../../shared/ui/classes.js";

export default function GenerationJobRow({ job, onSelect, onOpenWorld, onPlayWorld, onRestartJob }) {
  const canOpen = job.status === "done" && job.world_id;
  const canRestart = job.status === "failed";

  return (
    <article className="border-b border-[#2e2e2c] last:border-b-0">
      <button
        className="grid w-full grid-cols-[18px_12px_minmax(0,1fr)] items-center gap-2.5 border-0 bg-transparent px-4 py-3.5 text-left text-inherit hover:bg-[#20201e] lg:grid-cols-[18px_12px_minmax(0,1fr)_auto]"
        onClick={() => onSelect(job.id)}
      >
        <ChevronRight className="text-[#aaa49a] transition-transform duration-150" size={16} />
        <span className={statusDotClass(job.status)} aria-hidden="true" />
        <span className="grid min-w-0 gap-[3px]">
          <span className="truncate text-sm font-semibold">{job.prompt}</span>
          <span className="truncate text-xs text-[#aaa49a]">{job.provider}/{job.model_name} - {formatDate(job.updated_at)}</span>
        </span>
        <span className="col-start-3 justify-self-start text-xs text-[#aaa49a] lg:col-auto lg:justify-self-end">{statusLabel(job.status)}</span>
      </button>

      {job.error ? <div className="px-4 pb-3 pl-[34px] text-xs leading-normal text-[#f0c6bd] lg:pl-14">{job.error}</div> : null}

      {canOpen || canRestart ? (
        <div className="flex justify-end px-4 pb-3.5 pl-[34px] lg:pl-14">
          {canRestart ? (
            <button className={cx(button, buttonSecondary)} onClick={() => onRestartJob(job.id)}>
              <RotateCcw size={16} />
              Restart
            </button>
          ) : null}
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
        </div>
      ) : null}
    </article>
  );
}
