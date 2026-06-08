import React from "react";
import { Plus, RefreshCw } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";
import {
  button,
  buttonPrimary,
  errorText,
  label,
  textarea,
} from "../../../shared/ui/classes.js";

export default function CreateWorldForm({ prompt, setPrompt, onSubmit, creating, error }) {
  return (
    <section className="grid max-w-[820px] gap-2.5 rounded-lg border border-[#2e2e2c] bg-[#171716] p-4">
      <label className={label} htmlFor="prompt">World prompt</label>
      <textarea
        className={textarea}
        id="prompt"
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        placeholder="A rain-beaten frontier around an old imperial road, with fortress politics, hungry forests, and towns that owe debts to the wrong people."
        rows={8}
      />
      <div className="flex min-h-10 items-center gap-3">
        <button className={cx(button, buttonPrimary)} onClick={onSubmit} disabled={creating || !prompt.trim()}>
          {creating ? <RefreshCw size={16} /> : <Plus size={16} />}
          {creating ? "Queueing" : "Generate world"}
        </button>
        {error ? <span className={errorText}>{error}</span> : null}
      </div>
    </section>
  );
}
