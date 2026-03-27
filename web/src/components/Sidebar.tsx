import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Trash2,
  PanelLeftClose,
  PanelLeft,
  MessageSquare,
  Bot,
  Zap,
  ChevronDown,
  Database,
  Cpu,
  Box,
} from "lucide-react";
import * as ScrollArea from "@radix-ui/react-scroll-area";
import * as Tooltip from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";
import { fetchProjects, fetchStatus } from "@/api";

const VERSION = "0.1.0";

export default function Sidebar() {
  const {
    projects,
    currentProject,
    setProjects,
    setCurrentProject,
    conversations,
    activeConversationId,
    createConversation,
    deleteConversation,
    setActiveConversation,
    sidebarOpen,
    toggleSidebar,
    agentMode,
    toggleAgentMode,
    systemStatus,
    setSystemStatus,
  } = useStore();

  const statusInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch projects on mount
  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, [setProjects]);

  // Fetch system status on mount + every 30s
  useEffect(() => {
    const load = () =>
      fetchStatus()
        .then(setSystemStatus)
        .catch(() => {});
    load();
    statusInterval.current = setInterval(load, 30_000);
    return () => {
      if (statusInterval.current) clearInterval(statusInterval.current);
    };
  }, [setSystemStatus]);

  const handleNewConversation = useCallback(() => {
    createConversation();
  }, [createConversation]);

  const sortedConversations = [...conversations].sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );

  /* ---- Project selector state ---- */
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const projectMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        projectMenuRef.current &&
        !projectMenuRef.current.contains(e.target as Node)
      ) {
        setProjectMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  /* ---- Status dot helper ---- */
  const StatusDot = ({ ok }: { ok: boolean }) => (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full shrink-0",
        ok ? "bg-success" : "bg-error",
      )}
    />
  );

  /* ---- Render ---- */
  return (
    <Tooltip.Provider delayDuration={300}>
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.aside
            key="sidebar"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="shrink-0 overflow-hidden bg-dark-surface border-r border-dark-border flex flex-col h-full"
          >
            {/* ===== 1. Logo area ===== */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border">
              <div className="flex items-center gap-2 min-w-0">
                <div className="h-7 w-7 rounded-lg bg-accent flex items-center justify-center">
                  <Zap className="h-4 w-4 text-white" />
                </div>
                <span className="font-semibold text-dark-text tracking-wide truncate">
                  Delphi
                </span>
                <span className="text-[10px] text-dark-muted font-mono">
                  v{VERSION}
                </span>
              </div>
              <button
                onClick={toggleSidebar}
                className="p-1.5 rounded-md text-dark-muted hover:text-dark-text hover:bg-dark-hover transition-colors"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </div>

            {/* ===== 2. New conversation button ===== */}
            <div className="px-3 pt-3 pb-1">
              <button
                onClick={handleNewConversation}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                  "bg-accent/10 text-accent hover:bg-accent/20 border border-accent/20",
                )}
              >
                <Plus className="h-4 w-4" />
                新建对话
              </button>
            </div>

            {/* ===== 3. Conversation history ===== */}
            <ScrollArea.Root className="flex-1 min-h-0">
              <ScrollArea.Viewport className="h-full w-full px-2 py-1">
                {sortedConversations.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-dark-muted">
                    <MessageSquare className="h-8 w-8 mb-2 opacity-40" />
                    <p className="text-xs">暂无对话</p>
                    <p className="text-[11px] mt-1 opacity-60">
                      点击上方按钮开始
                    </p>
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    {sortedConversations.map((conv) => {
                      const isActive = conv.id === activeConversationId;
                      return (
                        <div
                          key={conv.id}
                          role="button"
                          tabIndex={0}
                          onClick={() => setActiveConversation(conv.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ")
                              setActiveConversation(conv.id);
                          }}
                          className={cn(
                            "group flex items-center gap-2 px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors",
                            isActive
                              ? "bg-dark-card text-dark-text"
                              : "text-dark-muted hover:bg-dark-hover hover:text-dark-text",
                          )}
                        >
                          <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-50" />
                          <span className="truncate flex-1 text-left">
                            {conv.title.length > 30
                              ? conv.title.slice(0, 30) + "..."
                              : conv.title}
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteConversation(conv.id);
                            }}
                            className={cn(
                              "p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity",
                              "text-dark-muted hover:text-error hover:bg-error/10",
                            )}
                            aria-label="Delete conversation"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </ScrollArea.Viewport>
              <ScrollArea.Scrollbar
                orientation="vertical"
                className="flex w-1.5 touch-none select-none p-0.5"
              >
                <ScrollArea.Thumb className="relative flex-1 rounded-full bg-dark-border" />
              </ScrollArea.Scrollbar>
            </ScrollArea.Root>

            {/* ===== Bottom section ===== */}
            <div className="border-t border-dark-border">
              {/* ---- 4. Project selector ---- */}
              <div className="px-3 py-2 relative" ref={projectMenuRef}>
                <button
                  onClick={() => setProjectMenuOpen((v) => !v)}
                  className={cn(
                    "w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors",
                    "bg-dark-card text-dark-text hover:bg-dark-hover border border-dark-border",
                  )}
                >
                  <span className="truncate">
                    {currentProject || "所有项目"}
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-dark-muted transition-transform",
                      projectMenuOpen && "rotate-180",
                    )}
                  />
                </button>
                <AnimatePresence>
                  {projectMenuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      transition={{ duration: 0.15 }}
                      className={cn(
                        "absolute left-3 right-3 bottom-full mb-1 z-50",
                        "bg-dark-card border border-dark-border rounded-lg shadow-xl overflow-hidden",
                      )}
                    >
                      <div className="max-h-48 overflow-y-auto py-1">
                        <button
                          onClick={() => {
                            setCurrentProject("");
                            setProjectMenuOpen(false);
                          }}
                          className={cn(
                            "w-full text-left px-3 py-2 text-sm transition-colors",
                            currentProject === ""
                              ? "bg-accent/10 text-accent"
                              : "text-dark-text hover:bg-dark-hover",
                          )}
                        >
                          所有项目
                        </button>
                        {projects.map((p) => (
                          <button
                            key={p.name}
                            onClick={() => {
                              setCurrentProject(p.name);
                              setProjectMenuOpen(false);
                            }}
                            className={cn(
                              "w-full text-left px-3 py-2 text-sm transition-colors flex items-center justify-between",
                              currentProject === p.name
                                ? "bg-accent/10 text-accent"
                                : "text-dark-text hover:bg-dark-hover",
                            )}
                          >
                            <span className="truncate">{p.name}</span>
                            <span className="text-[11px] text-dark-muted ml-2 shrink-0">
                              {p.chunk_count} chunks
                            </span>
                          </button>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* ---- 5. Mode toggle ---- */}
              <div className="px-3 py-2">
                <button
                  onClick={toggleAgentMode}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                    agentMode
                      ? "bg-accent/15 text-accent border border-accent/30"
                      : "bg-dark-card text-dark-muted hover:bg-dark-hover border border-dark-border",
                  )}
                >
                  <Bot className="h-4 w-4" />
                  <span className="flex-1 text-left">
                    {agentMode ? "Agent 模式" : "RAG 模式"}
                  </span>
                  <div
                    className={cn(
                      "w-8 h-[18px] rounded-full relative transition-colors",
                      agentMode ? "bg-accent" : "bg-dark-border",
                    )}
                  >
                    <motion.div
                      layout
                      className="absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white"
                      animate={{ left: agentMode ? 15 : 2 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  </div>
                </button>
              </div>

              {/* ---- 6. System status ---- */}
              <div className="px-3 py-2.5 flex items-center gap-3">
                {(
                  [
                    { key: "vllm", label: "vLLM", icon: Cpu },
                    { key: "qdrant", label: "Qdrant", icon: Database },
                    { key: "embedding", label: "Embedding", icon: Box },
                  ] as const
                ).map(({ key, label, icon: Icon }) => {
                  const svc = systemStatus?.[key];
                  const ok = svc?.ok ?? false;
                  const detail = svc
                    ? svc.ok
                      ? `${label}: 正常${svc.model ? ` (${svc.model})` : ""}${svc.collections != null ? ` - ${svc.collections} collections` : ""}`
                      : `${label}: ${svc.error || "异常"}`
                    : `${label}: 检测中...`;

                  return (
                    <Tooltip.Root key={key}>
                      <Tooltip.Trigger asChild>
                        <div className="flex items-center gap-1.5 cursor-default">
                          <Icon className="h-3.5 w-3.5 text-dark-muted" />
                          <StatusDot ok={ok} />
                        </div>
                      </Tooltip.Trigger>
                      <Tooltip.Portal>
                        <Tooltip.Content
                          side="top"
                          sideOffset={8}
                          className="z-50 rounded-md bg-dark-card border border-dark-border px-3 py-1.5 text-xs text-dark-text shadow-lg"
                        >
                          {detail}
                          <Tooltip.Arrow className="fill-dark-card" />
                        </Tooltip.Content>
                      </Tooltip.Portal>
                    </Tooltip.Root>
                  );
                })}
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Collapsed toggle button */}
      {!sidebarOpen && (
        <motion.button
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          onClick={toggleSidebar}
          className="fixed top-3 left-3 z-50 p-2 rounded-lg bg-dark-surface border border-dark-border text-dark-muted hover:text-dark-text hover:bg-dark-hover transition-colors"
          aria-label="Expand sidebar"
        >
          <PanelLeft className="h-4 w-4" />
        </motion.button>
      )}
    </Tooltip.Provider>
  );
}
