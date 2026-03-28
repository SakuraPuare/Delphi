import { useState } from "react";
import { Brain, Wrench, ClipboardList, ChevronDown } from "lucide-react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { cn } from "@/lib/utils";
import type { AgentStep } from "@/types";

interface AgentStepsProps {
  steps: AgentStep[];
}

export function AgentSteps({ steps }: AgentStepsProps) {
  const [open, setOpen] = useState(false);

  if (steps.length === 0) return null;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="my-2">
      <Collapsible.Trigger className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
        <Brain className="h-3 w-3" />
        Agent ({steps.length} steps)
        <ChevronDown
          className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
        />
      </Collapsible.Trigger>
      <Collapsible.Content className="mt-2 space-y-2 border-l-2 border-zinc-800 pl-3">
        {steps.map((step, i) => (
          <div key={i} className="space-y-1 text-xs">
            {step.thought && (
              <div className="flex items-start gap-1.5">
                <Brain className="mt-0.5 h-3 w-3 shrink-0 text-purple-400" />
                <span className="text-zinc-400">{step.thought}</span>
              </div>
            )}
            {step.action && (
              <div className="flex items-start gap-1.5">
                <Wrench className="mt-0.5 h-3 w-3 shrink-0 text-blue-400" />
                <span className="font-mono text-zinc-400">{step.action}</span>
              </div>
            )}
            {step.observation && (
              <div className="flex items-start gap-1.5">
                <ClipboardList className="mt-0.5 h-3 w-3 shrink-0 text-green-400" />
                <span className="text-zinc-500">{step.observation}</span>
              </div>
            )}
          </div>
        ))}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
