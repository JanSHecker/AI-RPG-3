import React, { useEffect } from "react";
import { X } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";
import { formatStepPayload, statusLabel } from "../../../shared/lib/format.js";
import {
  emptyPanel,
  h2,
  h3,
  iconButton,
  muted,
} from "../../../shared/ui/classes.js";

const responseBlock = "m-0 overflow-auto break-words whitespace-pre-wrap rounded-lg border border-[#2e2e2c] bg-[#111111] p-3 font-mono text-xs leading-[1.55] text-[#eeeeec]";

export default function StepDetailDrawer({ instance, title, onClose }) {
  useEffect(() => {
    if (!instance) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [instance, onClose]);

  if (!instance) return null;

  const promptMessages = Array.isArray(instance.prompt_messages) ? instance.prompt_messages : [];
  const responseText = instance.raw_response || formatStepPayload(instance.parsed_payload);
  const meta = [
    statusLabel(instance.status),
    `Attempts ${instance.attempts ?? 0}`,
    instance.latency_ms != null ? `${instance.latency_ms} ms` : "",
  ].filter(Boolean).join(" - ");

  return (
    <div className="fixed inset-0 z-20 flex justify-end" role="presentation">
      <button className="absolute inset-0 border-0 bg-black/45" type="button" onClick={onClose} aria-label="Close step detail" />
      <aside className="relative flex h-screen w-[min(760px,calc(100vw-24px))] flex-col border-l border-[#35332f] bg-[#171716]" role="dialog" aria-modal="true" aria-labelledby="step-detail-title">
        <div className="flex items-start justify-between gap-4 border-b border-[#2e2e2c] p-[18px]">
          <div className="min-w-0">
            <h2 id="step-detail-title" className={h2}>{title || instance.label || "Generator step"}</h2>
            <div className={muted}>{meta}</div>
          </div>
          <button className={iconButton} type="button" onClick={onClose} title="Close">
            <X size={16} />
          </button>
        </div>

        <div className="grid min-h-0 gap-[18px] overflow-auto p-[18px]">
          <section className="min-w-0">
            <h3 className={cx(h3, "mb-2.5")}>Sent prompt</h3>
            {promptMessages.length > 0 ? (
              <div className="grid gap-2.5">
                {promptMessages.map((message, index) => (
                  <article key={`${message.role ?? "message"}-${index}`} className="overflow-hidden rounded-lg border border-[#2e2e2c] bg-[#111111]">
                    <div className="border-b border-[#2e2e2c] px-2.5 py-2 text-xs font-semibold text-[#d8d3ca]">{message.role || `message ${index + 1}`}</div>
                    <pre className="m-0 overflow-auto break-words whitespace-pre-wrap p-3 font-mono text-xs leading-[1.55] text-[#eeeeec]">{message.content || ""}</pre>
                  </article>
                ))}
              </div>
            ) : (
              <div className={emptyPanel}>Sent prompt unavailable for this job.</div>
            )}
          </section>

          <section className="min-w-0">
            <h3 className={cx(h3, "mb-2.5")}>Response</h3>
            {responseText ? <pre className={responseBlock}>{responseText}</pre> : <div className={emptyPanel}>No response recorded yet.</div>}
          </section>
        </div>
      </aside>
    </div>
  );
}
