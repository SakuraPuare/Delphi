import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { motion } from "framer-motion";
import { Copy, Check } from "lucide-react";
import { cn, relativeTime } from "@/lib/utils";
import type { Message } from "@/types";
import SourceCard from "./SourceCard";

interface Props {
  message: Message;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const isStreaming = message.streaming === true;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "rounded-2xl px-4 py-3",
          isUser
            ? "max-w-[80%] bg-accent text-white"
            : "w-full bg-dark-card text-dark-text",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {message.content}
          </p>
        ) : (
          <>
            <div className="prose max-w-none text-sm leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={{ pre: CodeBlockWrapper }}
              >
                {message.content}
              </ReactMarkdown>
              {isStreaming && (
                <span className="inline-block h-5 w-2 animate-pulse rounded-sm bg-accent align-middle">
                  ▊
                </span>
              )}
            </div>
            {message.sources && message.sources.length > 0 && (
              <div className="mt-3">
                <SourceCard sources={message.sources} />
              </div>
            )}
          </>
        )}

        {/* 时间戳 */}
        {message.timestamp && (
          <p
            className={cn(
              "mt-1.5 text-[11px]",
              isUser ? "text-white/60" : "text-dark-muted",
            )}
          >
            {relativeTime(message.timestamp)}
          </p>
        )}
      </div>
    </motion.div>
  );
}

/* 代码块包装器 — 右上角复制按钮 */
function CodeBlockWrapper(props: React.ComponentPropsWithoutRef<"pre">) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    const code =
      (props.children as React.ReactElement<{ children?: string }>)?.props
        ?.children ?? "";
    navigator.clipboard.writeText(String(code)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [props.children]);

  return (
    <div className="group relative">
      <pre
        {...props}
        className={cn(props.className, "font-[JetBrains_Mono,monospace]")}
      />
      <button
        onClick={handleCopy}
        className={cn(
          "absolute right-2 top-2 rounded-md border border-dark-border bg-dark-surface p-1.5",
          "text-dark-muted opacity-0 transition-opacity hover:text-dark-text",
          "group-hover:opacity-100",
          copied && "opacity-100",
        )}
        aria-label={copied ? "已复制" : "复制代码"}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-success" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
    </div>
  );
}
