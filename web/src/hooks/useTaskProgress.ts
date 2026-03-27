import { useEffect, useRef, useCallback, useState } from "react";
import type { TaskProgress } from "@/types";

/** 构建 WebSocket URL：自动适配 http/https -> ws/wss */
function buildWsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api${path}`;
}

interface UseTaskProgressOptions {
  /** 订阅特定任务 ID，不传则订阅全部 */
  taskId?: string;
  /** 是否自动连接，默认 true */
  enabled?: boolean;
  /** 重连间隔（ms），默认 3000 */
  reconnectInterval?: number;
}

interface UseTaskProgressReturn {
  /** 当前所有任务的最新状态（按 task_id 索引） */
  tasks: Record<string, TaskProgress>;
  /** WebSocket 连接状态 */
  connected: boolean;
}

/**
 * React hook：通过 WebSocket 订阅任务进度。
 *
 * 用法：
 * ```tsx
 * const { tasks, connected } = useTaskProgress();
 * const { tasks } = useTaskProgress({ taskId: "abc123" });
 * ```
 */
export function useTaskProgress(options: UseTaskProgressOptions = {}): UseTaskProgressReturn {
  const { taskId, enabled = true, reconnectInterval = 3000 } = options;

  const [tasks, setTasks] = useState<Record<string, TaskProgress>>({});
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as TaskProgress;
      setTasks((prev) => ({ ...prev, [data.task_id]: data }));
    } catch {
      // skip malformed JSON
    }
  }, []);

  const connect = useCallback(() => {
    if (!enabled) return;

    const path = taskId ? `/ws/tasks/${taskId}` : "/ws/tasks";
    const ws = new WebSocket(buildWsUrl(path));

    ws.onopen = () => setConnected(true);

    ws.onmessage = handleMessage;

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // 自动重连
      if (enabled) {
        reconnectTimer.current = setTimeout(connect, reconnectInterval);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [enabled, taskId, reconnectInterval, handleMessage]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { tasks, connected };
}
