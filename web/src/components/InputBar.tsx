import { useState, useRef, useCallback, useEffect } from "react";
import { Send, Square } from "lucide-react";
import { useStore } from "@/store";
import { queryStream, agentQueryStream } from "@/api";
import { cn } from "@/lib/utils";

export default function InputBar() {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const streaming = useStore((s) => s.streaming);
  const agentMode = useStore((s) => s.agentMode);

  const {
    createConversation,
    addMessage,
    appendToLastAssistantContent,
    setLastAssistantSources,
    setLastAssistantStreaming,
    setStreaming,
    setSessionId,
  } = useStore.getState();

  // auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 192) + "px"; // max ~6 lines
  }, [text]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleSend = useCallback(async () => {
    const question = text.trim();
    if (!question || streaming) return;

    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    // ensure active conversation
    let convId = useStore.getState().activeConversationId;
    if (!convId) {
      convId = createConversation();
    }
    // add user message
    addMessage({ role: "user", content: question });

    // add empty assistant placeholder
    addMessage({ role: "assistant", content: "", streaming: true });
    setStreaming(true);

    const project = useStore.getState().currentProject;
    const sid = useStore.getState().sessionId;

    try {
      const stream = agentMode
        ? agentQueryStream(question, project, 5, sid)
        : queryStream(question, project, 5, sid);

      for await (const event of stream) {
        // check if aborted
        if (!useStore.getState().streaming) break;

        switch (event.type) {
          case "token":
            appendToLastAssistantContent(event.content);
            break;
          case "sources":
            setLastAssistantSources(event.sources);
            break;
          case "done":
            if (event.session_id) setSessionId(event.session_id);
            break;
          case "error":
            appendToLastAssistantContent(`\n\n**Error:** ${event.message}`);
            break;
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // user cancelled, ignore
      } else {
        const msg = err instanceof Error ? err.message : "Unknown error";
        appendToLastAssistantContent(`\n\n**Error:** ${msg}`);
      }
    } finally {
      setLastAssistantStreaming(false);
      setStreaming(false);
      abortRef.current = null;
    }
  }, [text, streaming, agentMode]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="shrink-0 px-4 pb-4 pt-2">
      <div className="mx-auto max-w-3xl">
        <div
          className={cn(
            "relative rounded-2xl border bg-dark-card shadow-lg shadow-black/20 transition-colors",
            "border-dark-border focus-within:border-accent",
          )}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题... (Enter 发送, Shift+Enter 换行)"
            rows={1}
            disabled={streaming}
            className={cn(
              "w-full resize-none bg-transparent px-4 pt-3 pb-10 text-sm text-dark-text",
              "placeholder-dark-muted outline-none disabled:opacity-50",
            )}
            aria-label="Question input"
          />

          <div className="absolute bottom-2 right-2 flex items-center gap-1">
            {streaming ? (
              <button
                onClick={handleStop}
                className="flex items-center justify-center rounded-lg bg-error/80 p-2 text-white transition-colors hover:bg-error"
                aria-label="Stop generation"
              >
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!text.trim()}
                className={cn(
                  "flex items-center justify-center rounded-lg p-2 transition-colors",
                  "bg-accent text-white hover:bg-accent-hover",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                )}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        <p className="mt-2 text-center text-xs text-dark-muted">
          Delphi 基于 RAG 检索回答，内容仅供参考
        </p>
      </div>
    </div>
  );
}
