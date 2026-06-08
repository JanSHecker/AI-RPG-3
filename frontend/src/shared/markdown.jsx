import React from "react";

const responseBlockClass = "m-0 overflow-auto break-words whitespace-pre-wrap rounded-lg border border-[#2e2e2c] bg-[#111111] p-3 font-mono text-xs leading-[1.55] text-[#eeeeec]";

export const markdownComponents = {
  h1: ({ node, ...props }) => <h1 className="m-0 text-xl font-semibold text-[#eeeeec]" {...props} />,
  h2: ({ node, ...props }) => <h2 className="mt-[18px] mb-0 text-base font-semibold text-[#eeeeec]" {...props} />,
  h3: ({ node, ...props }) => <h3 className="mt-4 mb-0 text-sm font-semibold text-[#eeeeec]" {...props} />,
  p: ({ node, ...props }) => <p className="mt-2 text-sm leading-[1.55] text-[#d8d3ca]" {...props} />,
  ul: ({ node, ...props }) => <ul className="mt-2 list-disc pl-5 text-sm leading-[1.55] text-[#d8d3ca]" {...props} />,
  ol: ({ node, ...props }) => <ol className="mt-2 list-decimal pl-5 text-sm leading-[1.55] text-[#d8d3ca]" {...props} />,
  li: ({ node, ...props }) => <li className="mt-1" {...props} />,
  pre: ({ node, ...props }) => <pre className={responseBlockClass} {...props} />,
  code: ({ node, inline, ...props }) => inline ? <code className="rounded bg-[#111111] px-1 font-mono text-xs text-[#eeeeec]" {...props} /> : <code {...props} />,
};
