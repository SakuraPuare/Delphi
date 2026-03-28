import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, FileCode } from "lucide-react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { cn } from "@/lib/utils";
import type { Source } from "@/types";

interface SourceCardProps {
  sources: Source[];
}

export function SourceCard({ sources }: SourceCardProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="mt-2">
      <Collapsible.Trigger className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
        <FileCode className="h-3 w-3" />
        {t("chat.sources")} ({sources.length})
        <ChevronDown
          className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
        />
      </Collapsible.Trigger>
      <Collapsible.Content className="mt-2 space-y-1.5">
        {sources.map((src, i) => (
          <div
            key={i}
            className="rounded-md border border-zinc-800 bg-zinc-900 p-2 text-xs"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-zinc-300 truncate">{src.file}</span>
              {src.start_line != null && (
                <span className="text-zinc-600 shrink-0 ml-2">
                  L{src.start_line}
                  {src.end_line != null && src.end_line !== src.start_line && `-${src.end_line}`}
                </span>
              )}
            </div>
            {src.chunk && (
              <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-zinc-500">
                {src.chunk}
              </pre>
            )}
          </div>
        ))}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
