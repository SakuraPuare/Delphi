import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, Wrench, ClipboardList, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentStep } from "@/types";

interface Props {
  steps: AgentStep[];
}

export default function AgentSteps({ steps }: Props) {
  if (steps.length === 0) return null;

  return (
    <div className="relative ml-3 border-l border-dark-border pl-5">
      <AnimatePresence initial={false}>
        {steps.map((step, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25, delay: i * 0.05 }}
            className="relative pb-4 last:pb-0"
          >
            {/* 时间线节点 */}
            <div className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full border-2 border-dark-border bg-dark-surface" />

            <StepContent step={step} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function StepContent({ step }: { step: AgentStep }) {
  const [obsOpen, setObsOpen] = useState(false);

  return (
    <div className="space-y-2 text-sm">
      {/* Thought */}
      {step.thought && (
        <div className="flex items-start gap-2">
          <Brain className="mt-0.5 h-3.5 w-3.5 shrink-0 text-dark-muted" />
          <p className="italic text-dark-muted">{step.thought}</p>
        </div>
      )}

      {/* Action */}
      {step.action && (
        <div className="flex items-center gap-2">
          <Wrench className="h-3.5 w-3.5 shrink-0 text-accent" />
          <span className="rounded-md bg-accent-muted px-2 py-0.5 text-xs font-medium text-accent">
            {step.action}
          </span>
        </div>
      )}

      {/* Observation (折叠) */}
      {step.observation && (
        <div>
          <button
            onClick={() => setObsOpen(!obsOpen)}
            className="flex items-center gap-2 text-dark-muted transition-colors hover:text-dark-text"
          >
            <ClipboardList className="h-3.5 w-3.5 shrink-0" />
            <span className="text-xs">Observation</span>
            <ChevronDown
              className={cn(
                "h-3 w-3 transition-transform duration-200",
                obsOpen && "rotate-180",
              )}
            />
          </button>
          <AnimatePresence>
            {obsOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="overflow-hidden"
              >
                <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap rounded-lg border border-dark-border bg-dark-bg p-3 font-[JetBrains_Mono,monospace] text-[11px] leading-relaxed text-dark-text">
                  {step.observation}
                </pre>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Answer */}
      {step.answer && (
        <p className="font-medium text-dark-text">{step.answer}</p>
      )}
    </div>
  );
}