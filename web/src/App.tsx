import { useState, useCallback, useRef } from "react";
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import InputBar from "./components/InputBar";
import { queryStream } from "./api";
import type { Message, Source } from "./types";

export default function App() {
  const [project, setProject] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleSend = useCallback(
    async (question: string) => {
      if (!question.trim() || streaming) return;

      const userMsg: Message = { role: "user", content: question };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);

      // Placeholder for assistant message
      const assistantIdx = messages.length + 1;
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      const controller = new AbortController();
      abortRef.current = controller;

      let collectedSources: Source[] = [];

      try {
        await queryStream(
          {
            question,
            project,
            top_k: 5,
            session_id: sessionId,
          },
          (event) => {
            switch (event.type) {
              case "token":
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[assistantIdx];
                  if (last) {
                    updated[assistantIdx] = {
                      ...last,
                      content: last.content + event.content,
                    };
                  }
                  return updated;
                });
                break;
              case "sources":
                collectedSources = event.sources;
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[assistantIdx];
                  if (last) {
                    updated[assistantIdx] = { ...last, sources: event.sources };
                  }
                  return updated;
                });
                break;
              case "done":
                if (event.session_id) setSessionId(event.session_id);
                break;
              case "error":
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[assistantIdx];
                  if (last) {
                    updated[assistantIdx] = {
                      ...last,
                      content: last.content || event.message,
                    };
                  }
                  return updated;
                });
                break;
            }
          },
          controller.signal
        );
      } catch (err: any) {
        if (err.name !== "AbortError") {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[assistantIdx];
            if (last) {
              updated[assistantIdx] = {
                ...last,
                content: `Error: ${err.message}`,
              };
            }
            return updated;
          });
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [project, sessionId, streaming, messages.length]
  );

  const handleProjectChange = useCallback((name: string) => {
    setProject(name);
    setMessages([]);
    setSessionId(null);
  }, []);

  return (
    <div className="flex h-screen">
      <Sidebar
        currentProject={project}
        onSelectProject={handleProjectChange}
      />
      <div className="flex flex-col flex-1 min-w-0">
        <header className="flex items-center h-12 px-4 border-b border-dark-border bg-dark-surface shrink-0">
          <h1 className="text-lg font-semibold tracking-wide">Delphi</h1>
          {project && (
            <span className="ml-3 text-sm text-dark-muted">/ {project}</span>
          )}
        </header>
        <ChatPanel messages={messages} streaming={streaming} />
        <InputBar onSend={handleSend} disabled={streaming} />
      </div>
    </div>
  );
}
