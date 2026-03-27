import { useEffect, useRef, useCallback } from "react";
import * as ScrollArea from "@radix-ui/react-scroll-area";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Loader2 } from "lucide-react";
import { useStore } from "@/store";
import { cn } from "@/lib/utils";
import MessageBubble from "./MessageBubble";

const SUGGESTIONS = [
  "这个项目的架构是什么？",
  "如何配置 vLLM 参数？",
  "解释一下 RAG 的工作原理",
];

export default function ChatPanel() {
  const conversation = useStore((s) => s.getActiveConversation());
  const streaming = useStore((s) => s.streaming);
  const addMessage = useStore((s) => s.addMessage);
  const messages = conversation?.messages ?? [];

  const viewportRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, messages[messages.length - 1]?.content]);

  const handleSuggestion = useCallback(
    (text: string) => {
      addMessage({ role: "user", content: text });
    },
    [addMessage],
  );

  return (
    <ScrollArea.Root className="flex-1 overflow-hidden">
      <ScrollArea.Viewport ref={viewportRef} className="h-full w-full">
        <div className="mx-auto max-w-[768px] px-4 py-6">
          {messages.length === 0 ? (
            <EmptyState onSuggestion={handleSuggestion} />
          ) : (
            <div className="space-y-4">
              <AnimatePresence initial={false}>
                {messages.map((msg, i) => (
                  <MessageBubble key={msg.id ?? i} message={msg} />
                ))}
              </AnimatePresence>
            </div>
          )}

          {/* 流式输出思考指示器 */}
          {streaming && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 py-3 text-sm text-dark-muted"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>正在思考...</span>
            </motion.div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea.Viewport>
      <ScrollArea.Scrollbar
        orientation="vertical"
        className="flex w-2 touch-none select-none p-0.5"
      >
        <ScrollArea.Thumb className="relative flex-1 rounded-full bg-dark-border" />
      </ScrollArea.Scrollbar>
    </ScrollArea.Root>
  );
}

function EmptyState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="flex flex-col items-center text-center"
      >
        <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-muted">
          <Sparkles className="h-8 w-8 text-accent" />
        </div>
        <h2 className="text-2xl font-semibold text-dark-text">Delphi</h2>
        <p className="mt-1 text-sm text-dark-muted">你的本地知识库助手</p>

        <div className="mt-8 w-full max-w-md">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-dark-muted">
            试试这些问题
          </p>
          <div className="grid gap-2">
            {SUGGESTIONS.map((text) => (
              <button
                key={text}
                onClick={() => onSuggestion(text)}
                className={cn(
                  "rounded-lg border border-dark-border bg-dark-card px-4 py-3",
                  "text-left text-sm text-dark-text",
                  "transition-colors hover:border-accent/40 hover:bg-dark-hover",
                )}
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
