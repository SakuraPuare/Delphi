import { create } from "zustand";
import type { Conversation, Message, ProjectInfo, Source, SystemStatus } from "@/types";

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

interface AppState {
  // 项目
  projects: ProjectInfo[];
  currentProject: string;
  setProjects: (projects: ProjectInfo[]) => void;
  setCurrentProject: (project: string) => void;

  // 对话
  conversations: Conversation[];
  activeConversationId: string | null;
  createConversation: () => string;
  deleteConversation: (id: string) => void;
  setActiveConversation: (id: string | null) => void;
  getActiveConversation: () => Conversation | undefined;

  // 消息
  addMessage: (msg: Omit<Message, "id" | "timestamp">) => void;
  updateLastAssistantMessage: (update: Partial<Message>) => void;
  appendToLastAssistantContent: (token: string) => void;
  setLastAssistantSources: (sources: Source[]) => void;
  setLastAssistantStreaming: (streaming: boolean) => void;

  // Session
  sessionId: string | null;
  setSessionId: (id: string | null) => void;

  // UI 状态
  streaming: boolean;
  setStreaming: (v: boolean) => void;
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  agentMode: boolean;
  toggleAgentMode: () => void;

  // 系统状态
  systemStatus: SystemStatus | null;
  setSystemStatus: (status: SystemStatus) => void;
}

export const useStore = create<AppState>((set, get) => ({
  // 项目
  projects: [],
  currentProject: "",
  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => {
    const state = get();
    if (project !== state.currentProject) {
      set({ currentProject: project, sessionId: null });
    }
  },

  // 对话
  conversations: [],
  activeConversationId: null,
  createConversation: () => {
    const id = generateId();
    const conv: Conversation = {
      id,
      title: "新对话",
      project: get().currentProject,
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    set((s) => ({
      conversations: [conv, ...s.conversations],
      activeConversationId: id,
      sessionId: null,
    }));
    return id;
  },
  deleteConversation: (id) =>
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      activeConversationId: s.activeConversationId === id ? null : s.activeConversationId,
    })),
  setActiveConversation: (id) => set({ activeConversationId: id, sessionId: null }),
  getActiveConversation: () => {
    const { conversations, activeConversationId } = get();
    return conversations.find((c) => c.id === activeConversationId);
  },

  // 消息
  addMessage: (msg) =>
    set((s) => {
      const convId = s.activeConversationId;
      if (!convId) return s;
      const message: Message = { ...msg, id: generateId(), timestamp: Date.now() };
      return {
        conversations: s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: [...c.messages, message],
                title: c.messages.length === 0 && msg.role === "user" ? msg.content.slice(0, 30) : c.title,
                updatedAt: Date.now(),
              }
            : c,
        ),
      };
    }),
  updateLastAssistantMessage: (update) =>
    set((s) => {
      const convId = s.activeConversationId;
      if (!convId) return s;
      return {
        conversations: s.conversations.map((c) => {
          if (c.id !== convId) return c;
          const msgs = [...c.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, ...update };
          }
          return { ...c, messages: msgs, updatedAt: Date.now() };
        }),
      };
    }),
  appendToLastAssistantContent: (token) =>
    set((s) => {
      const convId = s.activeConversationId;
      if (!convId) return s;
      return {
        conversations: s.conversations.map((c) => {
          if (c.id !== convId) return c;
          const msgs = [...c.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, content: last.content + token };
          }
          return { ...c, messages: msgs };
        }),
      };
    }),
  setLastAssistantSources: (sources) =>
    set((s) => {
      const convId = s.activeConversationId;
      if (!convId) return s;
      return {
        conversations: s.conversations.map((c) => {
          if (c.id !== convId) return c;
          const msgs = [...c.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, sources };
          }
          return { ...c, messages: msgs };
        }),
      };
    }),
  setLastAssistantStreaming: (streaming) =>
    set((s) => {
      const convId = s.activeConversationId;
      if (!convId) return s;
      return {
        conversations: s.conversations.map((c) => {
          if (c.id !== convId) return c;
          const msgs = [...c.messages];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant") {
            msgs[msgs.length - 1] = { ...last, streaming };
          }
          return { ...c, messages: msgs };
        }),
      };
    }),

  // Session
  sessionId: null,
  setSessionId: (id) => set({ sessionId: id }),

  // UI
  streaming: false,
  setStreaming: (v) => set({ streaming: v }),
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  agentMode: false,
  toggleAgentMode: () => set((s) => ({ agentMode: !s.agentMode })),

  // 系统状态
  systemStatus: null,
  setSystemStatus: (status) => set({ systemStatus: status }),
}));
