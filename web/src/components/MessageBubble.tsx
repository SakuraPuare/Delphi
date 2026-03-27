import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import SourceCard from "./SourceCard";
import type { Message } from "../types";

interface Props {
  message: Message;
  isStreaming: boolean;
}

export default function MessageBubble({ message, isStreaming }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[90%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-dark-accent text-white"
            : "bg-dark-surface text-dark-text"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            <div className="prose prose-invert max-w-none text-sm leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {message.content}
              </ReactMarkdown>
              {isStreaming && (
                <span className="inline-block w-2 h-4 ml-0.5 bg-dark-text animate-pulse rounded-sm" />
              )}
            </div>
            {message.sources && message.sources.length > 0 && (
              <div className="mt-3 pt-3 border-t border-dark-border space-y-2">
                <p className="text-xs text-dark-muted font-semibold uppercase tracking-wider">
                  Sources
                </p>
                {message.sources.map((src) => (
                  <SourceCard key={src.index} source={src} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
