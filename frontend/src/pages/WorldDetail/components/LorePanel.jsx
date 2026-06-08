import React from "react";
import ReactMarkdown from "react-markdown";
import { emptyPanel } from "../../../shared/ui/classes.js";
import { markdownComponents } from "../../../shared/markdown.jsx";

export default function LorePanel({ lore, loading }) {
  return (
    <aside className="max-h-none overflow-auto rounded-lg border border-[#2e2e2c] bg-[#171716] p-4 lg:max-h-[calc(100vh-125px)]">
      {loading ? (
        <div className={emptyPanel}>Loading lore...</div>
      ) : lore ? (
        <ReactMarkdown components={markdownComponents}>{lore}</ReactMarkdown>
      ) : (
        <div className={emptyPanel}>Select a record to read lore.</div>
      )}
    </aside>
  );
}
