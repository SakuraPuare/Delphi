import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useOutletContext } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Send, Square, Bot, Sparkles, Loader2 } from "lucide-react";
import { useChatStore } from "@/stores/chat-store";
import { useConversations, useMessages } from "@/hooks/use-conversations";
import { useSSEStream } from "@/hooks/use-sse-stream";
import { projectsQueryOptions } from "@/queries/projects";
import { MessageBubble } from "@/components/chat/MessageBubble";
import { AgentSteps } from "@/components/chat/AgentSteps";
import { ConversationList } from "@/components/chat/ConversationList";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import * as ScrollArea from "@radix-ui/react-scroll-area";

export function ChatPage() {
  const { t } = useTranslation();
  const { conversationId: urlConvId } = useParams();
  const outletCtx = useOutletContext<{ projectName?: string }>();
  const projectScope = outletCtx?.projectName ?? "";

  const { data: projects } = useQuery(projectsQueryOptions);
  const [selectedProject, setSelectedProject] = useState(projectScope);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    activeConversationId,
    setActiveConversation,
    messages: streamMessages,
    setMessages,
    isStreaming,
    streamingContent,
    streamingSteps,
    agentMode,
    setAgentMode,
    addUserMessage,
  } = useChatStore();

  const { conversations, createConversation, deleteConversation, updateConversation } =
    useConversations(projectScope || undefined);
  const { messages: dbMessages, addMessage } = useMessages(activeConversationId);
  const { startStream, stopStream } = useSSEStream();

  // Sync DB messages to store
  useEffect(() => {
    if (dbMessages.length > 0) {
      setMessages(
        dbMessages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          sources: m.sources,
          agentSteps: m.agentSteps,
          createdAt: m.createdAt,
        })),
      );
    }
  }, [dbMessages, setMessages]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamMessages, streamingContent]);

  // Set active conversation from URL
  useEffect(() => {
    if (urlConvId && urlConvId !== activeConversationId) {
      setActiveConversation(urlConvId);
    }
  }, [urlConvId, activeConversationId, setActiveConversation]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");

    let convId = activeConversationId;
    if (!convId) {
      const conv = await createConversation(text.slice(0, 30), selectedProject);
      convId = conv.id;
      setActiveConversation(convId);
    }

    const userMsg = addUserMessage(text);
    await addMessage({
      conversationId: convId,
      role: "user",
      content: text,
      createdAt: userMsg.createdAt,
    });

    try {
      await startStream(text, selectedProject, agentMode);
      // Save assistant message to DB
      const state = useChatStore.getState();
      const lastMsg = state.messages[state.messages.length - 1];
      if (lastMsg?.role === "assistant") {
        await addMessage({
          conversationId: convId,
          role: "assistant",
          content: lastMsg.content,
          sources: lastMsg.sources,
          agentSteps: lastMsg.agentSteps,
          createdAt: lastMsg.createdAt,
        });
        if (state.sessionId) {
          await updateConversation(convId, { sessionId: state.sessionId });
        }
      }
    } catch {
      // Error already handled in hook
    }
  }, [input, isStreaming, activeConversationId, selectedProject, agentMode, addUserMessage, addMessage, startStream, createConversation, setActiveConversation, updateConversation]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestions = t("chat.suggestions", { returnObjects: true }) as string[];

  return (
    <div className="flex h-full">
      {/* Conversation List (only in global chat, not project-scoped) */}
      {!projectScope && (
        <div className="w-64 shrink-0 border-r border-zinc-800">
          <ConversationList
            conversations={conversations}
            activeId={activeConversationId}
            onSelect={(id) => setActiveConversation(id)}
            onDelete={deleteConversation}
            onNew={() => setActiveConversation(null)}
          />
        </div>
      )}

      {/* Chat Area */}
      <div className="flex flex-1 flex-col">
        <ScrollArea.Root className="flex-1">
          <ScrollArea.Viewport className="h-full w-full">
            <div className="mx-auto max-w-3xl px-4 py-6">
              {streamMessages.length === 0 && !isStreaming ? (
                /* Empty state with suggestions */
                <div className="flex flex-col items-center justify-center py-20">
                  <Sparkles className="h-12 w-12 text-zinc-700 mb-4" />
                  <p className="text-lg text-zinc-500 mb-6">{t("chat.placeholder")}</p>
                  <div className="grid grid-cols-2 gap-3 max-w-lg">
                    {suggestions.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          setInput(s);
                          // Trigger send after state update
                          setTimeout(() => {
                            const el = document.querySelector<HTMLButtonElement>("[data-send-btn]");
                            el?.click();
                          }, 50);
                        }}
                        className="rounded-lg border border-zinc-800 p-3 text-left text-sm text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-200"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                /* Messages */
                <div className="space-y-4">
                  {streamMessages.map((msg) => (
                    <div key={msg.id}>
                      <MessageBubble message={msg} />
                      {msg.agentSteps && msg.agentSteps.length > 0 && (
                        <AgentSteps steps={msg.agentSteps} />
                      )}
                    </div>
                  ))}
                  {/* Streaming message */}
                  {isStreaming && (
                    <div>
                      {streamingSteps.length > 0 && (
                        <AgentSteps steps={streamingSteps} />
                      )}
                      {streamingContent ? (
                        <MessageBubble
                          message={{
                            id: "streaming",
                            role: "assistant",
                            content: streamingContent,
                            createdAt: Date.now(),
                          }}
                        />
                      ) : (
                        <div className="flex items-center gap-2 text-zinc-500 text-sm">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          {t("chat.thinking")}
                        </div>
                      )}
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>
          </ScrollArea.Viewport>
          <ScrollArea.Scrollbar orientation="vertical" className="w-2">
            <ScrollArea.Thumb className="rounded-full bg-zinc-700" />
          </ScrollArea.Scrollbar>
        </ScrollArea.Root>

        {/* Input Bar */}
        <div className="border-t border-zinc-800 p-4">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-end gap-2">
              {/* Project selector */}
              {!projectScope && (
                <select
                  value={selectedProject}
                  onChange={(e) => setSelectedProject(e.target.value)}
                  className="h-10 rounded-md border border-zinc-700 bg-zinc-900 px-2 text-sm text-zinc-300"
                >
                  <option value="">{t("chat.allProjects")}</option>
                  {projects?.map((p) => (
                    <option key={p.name} value={p.name}>{p.name}</option>
                  ))}
                </select>
              )}

              {/* Text input */}
              <div className="relative flex-1">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={t("chat.placeholder")}
                  rows={1}
                  className={cn(
                    "w-full resize-none rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 pr-20 text-sm text-zinc-100",
                    "placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500",
                    "max-h-32",
                  )}
                  style={{ minHeight: "40px" }}
                />
                <div className="absolute bottom-1.5 right-2 flex items-center gap-1">
                  {/* Agent mode toggle */}
                  <button
                    onClick={() => setAgentMode(!agentMode)}
                    className={cn(
                      "rounded-md p-1.5 text-xs transition-colors",
                      agentMode
                        ? "bg-blue-600/20 text-blue-400"
                        : "text-zinc-500 hover:text-zinc-300",
                    )}
                    title={t("chat.agentMode")}
                  >
                    <Bot className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Send / Stop */}
              {isStreaming ? (
                <Button variant="destructive" size="icon" onClick={stopStream}>
                  <Square className="h-4 w-4" />
                </Button>
              ) : (
                <Button
                  size="icon"
                  onClick={handleSend}
                  disabled={!input.trim()}
                  data-send-btn
                >
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
