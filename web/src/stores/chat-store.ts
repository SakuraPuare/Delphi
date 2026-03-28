import { create } from "zustand";
import type { Message, Source, AgentStep } from "@/types";

interface ChatState {
  // Current conversation
  activeConversationId: string | null;
  messages: Message[];
  sessionId: string | null;
  isStreaming: boolean;
  streamingContent: string;
  streamingSources: Source[];
  streamingSteps: AgentStep[];
  agentMode: boolean;

  // Actions
  setActiveConversation: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  setSessionId: (id: string | null) => void;
  setStreaming: (streaming: boolean) => void;
  setAgentMode: (mode: boolean) => void;
  appendStreamToken: (token: string) => void;
  setStreamingSources: (sources: Source[]) => void;
  addAgentStep: (step: Partial<AgentStep>) => void;
  updateLastAgentStep: (update: Partial<AgentStep>) => void;
  finalizeAssistantMessage: (sessionId?: string) => Message | null;
  resetStream: () => void;
  addUserMessage: (content: string) => Message;
}

let msgCounter = 0;
const genId = () => `msg_${Date.now()}_${++msgCounter}`;

export const useChatStore = create<ChatState>((set, get) => ({
  activeConversationId: null,
  messages: [],
  sessionId: null,
  isStreaming: false,
  streamingContent: "",
  streamingSources: [],
  streamingSteps: [],
  agentMode: false,

  setActiveConversation: (id) =>
    set({ activeConversationId: id, messages: [], sessionId: null }),

  setMessages: (messages) => set({ messages }),

  setSessionId: (id) => set({ sessionId: id }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  setAgentMode: (mode) => set({ agentMode: mode }),

  appendStreamToken: (token) =>
    set((s) => ({ streamingContent: s.streamingContent + token })),

  setStreamingSources: (sources) => set({ streamingSources: sources }),

  addAgentStep: (step) =>
    set((s) => ({
      streamingSteps: [
        ...s.streamingSteps,
        { thought: step.thought || "", ...step },
      ],
    })),

  updateLastAgentStep: (update) =>
    set((s) => {
      const steps = [...s.streamingSteps];
      if (steps.length > 0) {
        steps[steps.length - 1] = { ...steps[steps.length - 1], ...update };
      }
      return { streamingSteps: steps };
    }),

  finalizeAssistantMessage: (sessionId) => {
    const s = get();
    if (!s.streamingContent && s.streamingSteps.length === 0) return null;
    const msg: Message = {
      id: genId(),
      role: "assistant",
      content: s.streamingContent,
      sources: s.streamingSources.length > 0 ? s.streamingSources : undefined,
      agentSteps: s.streamingSteps.length > 0 ? s.streamingSteps : undefined,
      createdAt: Date.now(),
    };
    set((prev) => ({
      messages: [...prev.messages, msg],
      sessionId: sessionId ?? prev.sessionId,
      streamingContent: "",
      streamingSources: [],
      streamingSteps: [],
      isStreaming: false,
    }));
    return msg;
  },

  resetStream: () =>
    set({
      streamingContent: "",
      streamingSources: [],
      streamingSteps: [],
      isStreaming: false,
    }),

  addUserMessage: (content) => {
    const msg: Message = {
      id: genId(),
      role: "user",
      content,
      createdAt: Date.now(),
    };
    set((s) => ({ messages: [...s.messages, msg] }));
    return msg;
  },
}));
