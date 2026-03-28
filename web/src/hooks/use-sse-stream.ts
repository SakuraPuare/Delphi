import { useCallback, useRef } from "react";
import { api } from "@/lib/api-client";
import { parseSSE } from "@/lib/sse";
import { useChatStore } from "@/stores/chat-store";
import type { StreamEvent } from "@/types";

/**
 * Hook for SSE streaming queries.
 * Handles both normal RAG and Agent mode streams.
 */
export function useSSEStream() {
  const abortRef = useRef<AbortController | null>(null);
  const store = useChatStore;

  const startStream = useCallback(
    async (question: string, project: string, agentMode: boolean) => {
      // Abort any existing stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const { sessionId } = store.getState();
      store.getState().setStreaming(true);

      const path = agentMode ? "/agent/query/stream" : "/query/stream";
      const body = agentMode
        ? { question, project: project || undefined, max_steps: 5, session_id: sessionId }
        : { question, project: project || undefined, top_k: 5, session_id: sessionId };

      try {
        const response = await api.stream(path, body, controller.signal);
        for await (const event of parseSSE(response)) {
          const e = event as unknown as StreamEvent;
          switch (e.type) {
            case "token":
              store.getState().appendStreamToken(e.content);
              break;
            case "sources":
              store.getState().setStreamingSources(e.sources);
              break;
            case "thought":
              store.getState().addAgentStep({ thought: e.content });
              break;
            case "action":
              store.getState().updateLastAgentStep({ action: e.content });
              break;
            case "observation":
              store.getState().updateLastAgentStep({ observation: e.content });
              break;
            case "done":
              store.getState().finalizeAssistantMessage(e.session_id);
              break;
            case "error":
              store.getState().resetStream();
              throw new Error(e.message);
          }
        }
        // If stream ends without a done event, finalize anyway
        if (store.getState().isStreaming) {
          store.getState().finalizeAssistantMessage();
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          store.getState().resetStream();
          throw err;
        }
      }
    },
    [],
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    const state = store.getState();
    if (state.streamingContent) {
      state.finalizeAssistantMessage();
    } else {
      state.resetStream();
    }
  }, []);

  return { startStream, stopStream };
}
