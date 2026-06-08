import React from "react";
import { cx } from "../../../shared/lib/classNames.js";
import { emptyPanel } from "../../../shared/ui/classes.js";

const baseMessage = "max-w-[780px] rounded-lg border border-[#2e2e2c] bg-[#151514] px-3 py-2.5 text-sm leading-[1.55] text-[#d8d3ca]";
const playerMessage = "justify-self-end border-[#5a4330] bg-[#201915]";
const npcMessage = "border-[#3a3834] bg-[#1d1d1b]";
const wideMessage = "max-w-none border-dashed text-[#c9c2b8]";

function playMessageClass(kind) {
  return cx(
    baseMessage,
    kind === "player" && playerMessage,
    kind === "npc" && npcMessage,
    ["travel", "system"].includes(kind) && wideMessage,
  );
}

export default function PlayLog({ messages, npcById, characterName }) {
  return (
    <div className="relative z-10 grid min-h-0 flex-1 content-start gap-2.5 overflow-auto px-4 py-3.5" aria-live="polite">
      {messages.length === 0 ? (
        <div className={emptyPanel}>No play messages yet.</div>
      ) : (
        messages.map((item) => {
          const npc = item.npc_id ? npcById.get(item.npc_id) : null;
          const title = item.kind === "player" ? characterName : item.kind === "npc" ? npc?.name || "NPC" : item.kind;
          return (
            <article key={item.id} className={playMessageClass(item.kind)}>
              <div className="mb-1 text-xs font-semibold text-[#aaa49a]">{title}</div>
              <div>{item.content}</div>
            </article>
          );
        })
      )}
    </div>
  );
}
