import { useEffect, useRef } from "react";
import { useTaskStore } from "@/stores/task-store";
import type { TaskProgress } from "@/types";

/**
 * WebSocket hook for real-time task progress.
 * Connects to /api/ws/tasks (all tasks) or /api/ws/tasks/:id (single task).
 */
export function useTaskProgress(taskId?: string) {
  const setTask = useTaskStore((s) => s.setTask);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const path = taskId ? `/api/ws/tasks/${taskId}` : "/api/ws/tasks";
    const url = `${proto}//${location.host}${path}`;

    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as TaskProgress;
          setTask({
            task_id: data.task_id,
            task_type: data.task_type,
            status: data.status,
            progress: data.progress,
            total: 0,
            processed: 0,
            message: data.message,
            metadata: data.metadata,
            result: data.result ?? undefined,
            error: data.error ?? undefined,
            created_at: data.created_at,
            updated_at: data.updated_at,
          });
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [taskId, setTask]);
}
