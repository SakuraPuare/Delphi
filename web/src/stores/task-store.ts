import { create } from "zustand";
import type { TaskInfo } from "@/types";

interface TaskState {
  tasks: Map<string, TaskInfo>;
  setTask: (task: TaskInfo) => void;
  removeTask: (taskId: string) => void;
  clearDone: () => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: new Map(),

  setTask: (task) =>
    set((s) => {
      const next = new Map(s.tasks);
      next.set(task.task_id, task);
      return { tasks: next };
    }),

  removeTask: (taskId) =>
    set((s) => {
      const next = new Map(s.tasks);
      next.delete(taskId);
      return { tasks: next };
    }),

  clearDone: () =>
    set((s) => {
      const next = new Map(s.tasks);
      for (const [id, t] of next) {
        if (t.status === "done" || t.status === "failed") next.delete(id);
      }
      return { tasks: next };
    }),
}));
