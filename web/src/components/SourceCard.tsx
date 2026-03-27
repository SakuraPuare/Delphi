import { useState } from "react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { motion, AnimatePresence } from "framer-motion";
import { FileCode, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Source } from "@/types";

interface Props {
  sources: Source[];
}

export default function SourceCard({ sources }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <Collapsible.Trigger
        className={cn(
          "flex w-full items-center gap-2 rounded-lg border border-dark-border px-3 py-2",
          "text-xs font-medium text-dark-muted transition-colors",
          "hover:bg-dark-hover",
        )}
      >
        <FileCode className="h-3.5 w-3.5" />
        <span>{sources.length} 个引用来源</span>
        <ChevronDown
          className={cn(
            "ml-auto h-3.5 w-3.5 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </Collapsible.Trigger>

      <AnimatePresence>
        {open && (
          <Collapsible.Content forceMount asChild>
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeInOut" }}
              className="overflow-hidden"
            >
              <div className="mt-2 grid grid-cols-2 gap-2">
                {sources.map((src) => (
                  <SourceItem key={src.index} source={src} />
                ))}
              </div>
            </motion.div>
          </Collapsible.Content>
        )}
      </AnimatePresence>
    </Collapsible.Root>
  );
}

function SourceItem({ source }: { source: Source }) {
  const [expanded, setExpanded] = useState(false);
  const scorePercent = Math.round(source.score * 100);

  const lineRange =
    source.start_line != null && source.end_line != null
      ? `L${source.start_line}-${source.end_line}`
      : null;

  return (
    <div
      className={cn(
        "rounded-lg border border-dark-border bg-dark-bg text-xs",
        "transition-colors hover:border-dark-muted/40",
        expanded && "col-span-2",
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        aria-expanded={expanded}
      >
        <FileCode className="h-3.5 w-3.5 shrink-0 text-dark-muted" />
        <span className="min-w-0 truncate text-dark-text">{source.file}</span>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {lineRange && (
            <span className="rounded bg-dark-hover px-1.5 py-0.5 text-[10px] text-dark-muted">
              {lineRange}
            </span>
          )}
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-medium",
              scorePercent > 80
                ? "bg-success/15 text-success"
                : scorePercent > 50
                  ? "bg-warning/15 text-warning"
                  : "bg-dark-hover text-dark-muted",
            )}
          >
            {scorePercent}%
          </span>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="border-t border-dark-border px-3 pb-3">
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded bg-dark-surface p-2 font-[JetBrains_Mono,monospace] text-[11px] leading-relaxed text-dark-text">
                {source.chunk}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
