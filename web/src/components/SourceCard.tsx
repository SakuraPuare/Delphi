import { useState } from "react";
import type { Source } from "../types";

interface Props {
  source: Source;
}

export default function SourceCard({ source }: Props) {
  const [expanded, setExpanded] = useState(false);

  const lineRange =
    source.start_line != null && source.end_line != null
      ? `L${source.start_line}-${source.end_line}`
      : null;

  const scorePercent = Math.round(source.score * 100);

  return (
    <div className="bg-dark-bg rounded border border-dark-border text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-dark-border/50 transition-colors text-left"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-dark-muted shrink-0">[{source.index}]</span>
          <span className="truncate text-dark-text">{source.file}</span>
          {lineRange && (
            <span className="text-dark-muted shrink-0">{lineRange}</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
              scorePercent >= 80
                ? "bg-green-900/50 text-green-400"
                : scorePercent >= 50
                ? "bg-yellow-900/50 text-yellow-400"
                : "bg-red-900/50 text-red-400"
            }`}
          >
            {scorePercent}%
          </span>
          <svg
            className={`w-3 h-3 text-dark-muted transition-transform ${
              expanded ? "rotate-180" : ""
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </div>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-dark-border">
          <pre className="mt-2 p-2 bg-[#0d1117] rounded text-[11px] text-dark-text overflow-x-auto whitespace-pre-wrap leading-relaxed">
            {source.chunk}
          </pre>
        </div>
      )}
    </div>
  );
}
