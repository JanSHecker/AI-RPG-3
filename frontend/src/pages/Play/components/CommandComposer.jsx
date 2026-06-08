import React, { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, Send } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";
import { label } from "../../../shared/ui/classes.js";
import { buildSuggestions, completionSuffix, splitCommandInput } from "../commands.js";

export default function CommandComposer({
  isConversation,
  conversationNpc,
  places,
  presentNpcs,
  inputLoading,
  onSubmit,
}) {
  const [commandInput, setCommandInput] = useState("");
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const highlightRef = useRef(null);

  const suggestions = useMemo(
    () => buildSuggestions({ commandInput, isConversation, places, presentNpcs }),
    [commandInput, isConversation, places, presentNpcs],
  );
  const activeSuggestion = suggestions[activeSuggestionIndex] ?? suggestions[0] ?? null;
  const activeCompletionSuffix = completionSuffix(commandInput, activeSuggestion?.value ?? "");
  const highlightedInput = splitCommandInput(commandInput);

  useEffect(() => {
    if (activeSuggestionIndex >= suggestions.length) {
      setActiveSuggestionIndex(0);
    }
  }, [activeSuggestionIndex, suggestions.length]);

  const submitCommand = async () => {
    const text = commandInput.trim();
    if (!text || inputLoading) return;
    await onSubmit(text);
    setCommandInput("");
  };

  const syncHighlightScroll = (event) => {
    if (!highlightRef.current) return;
    highlightRef.current.scrollTop = event.currentTarget.scrollTop;
    highlightRef.current.scrollLeft = event.currentTarget.scrollLeft;
  };

  const handleCommandKeyDown = (event) => {
    if (suggestions.length > 0 && event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (suggestions.length > 0 && event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current - 1 + suggestions.length) % suggestions.length);
      return;
    }
    if (suggestions.length > 0 && event.key === "Tab") {
      event.preventDefault();
      setCommandInput(activeSuggestion?.value ?? commandInput);
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitCommand().catch(() => {});
    }
  };

  return (
    <div className="relative z-10 mt-auto grid flex-none gap-0 border-t border-[#2e2e2c] bg-[#151514] p-2">
      <div className={label}>{isConversation && conversationNpc ? `Talking to ${conversationNpc.name}` : "Default mode"}</div>
      <div className="grid min-h-10 grid-cols-[minmax(0,1fr)_38px] items-stretch rounded-[7px] border border-[#3a3834] bg-[#111111]">
        <div className="relative min-h-[38px] min-w-0">
          <pre
            className="pointer-events-none absolute inset-0 m-0 max-h-24 min-h-[38px] w-full overflow-auto break-words whitespace-pre-wrap border-0 bg-transparent px-2.5 py-[9px] text-sm leading-[1.45] text-[#eeeeec]"
            ref={highlightRef}
            aria-hidden="true"
          >
            {highlightedInput.command ? <span className="text-[#b6d2b9]">{highlightedInput.command}</span> : null}
            {highlightedInput.rest ? <span className="text-[#d7c4a7]">{highlightedInput.rest}</span> : null}
            {activeCompletionSuffix ? <span className="text-[#6f6a63]">{activeCompletionSuffix}</span> : null}
          </pre>
          <textarea
            className={cx(
              "relative z-10 m-0 max-h-24 min-h-[38px] w-full resize-none overflow-auto break-words rounded-none border-0 bg-transparent px-2.5 py-[9px] text-sm leading-[1.45] text-[#eeeeec] caret-[#eeeeec] outline-none",
              commandInput && "text-transparent",
            )}
            value={commandInput}
            onChange={(event) => {
              setCommandInput(event.target.value);
              setActiveSuggestionIndex(0);
            }}
            onKeyDown={handleCommandKeyDown}
            onScroll={syncHighlightScroll}
            placeholder={isConversation && conversationNpc ? `Say something to ${conversationNpc.name} or type /exit` : "Type /travel <place> or /talk <character>"}
            rows={1}
            spellCheck="false"
            disabled={inputLoading}
          />
        </div>
        <button
          className="inline-flex min-h-[38px] w-[38px] cursor-pointer items-center justify-center rounded-r-md border-0 border-l border-[#3a3834] bg-[#20201e] text-[#d7c4a7] disabled:cursor-not-allowed disabled:opacity-[0.55]"
          type="button"
          onClick={() => submitCommand().catch(() => {})}
          disabled={!commandInput.trim() || inputLoading}
        >
          {inputLoading ? <RefreshCw size={16} /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}
