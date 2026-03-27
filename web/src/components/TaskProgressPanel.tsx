import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskProgress, TaskStatus } from "@/types";

const STATUS_CONFIG: Record<TaskStatus, { icon: typeof Loader2; color: string; label: string }> = {
  pending: { icon: Clock, color: "text-yellow-400", label: "等待中" },
  running: { icon: Loader2, color: "text-blue-400", label: "运行中" },
  done: { icon: CheckCircle2, color: "text-green-400", label: "完成" },
  failed: { icon: XCircle, color: "text-red-400", label: "失败" },
};

const TASK_TYPE_LABELS: Record<string, string> = {
  git_import: "Git 导入",
  doc_import: "文档导入",
  media_import: "媒体导入",
  finetune: "微调数据生成",
  graph_build: "图谱构建",
  import: "导入",
};

function TaskItem({ task }: { task: TaskProgress }) {
  const config = STATUS_CONFIG[task.status];
  const Icon = config.icon;
  const typeLabel = TASK_TYPE_LABELS[task.task_type] ?? task.task_type;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="rounded-lg bg-dark-surface border border-dark-border p-3 space-y-2"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-dark-text truncate">{typeLabel}</span>
        <div className={cn("flex items-center gap-1 text-xs", config.color)}>
          <Icon className={cn("h-3 w-3", task.status === "running" && "animate-spin")} />
          <span>{config.label}</span>
        </div>
      </div>

      {task.status === "running" && (
        <>
          <div className="w-full h-1.5 bg-dark-hover rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-blue-500 rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(task.progress, 100)}%` }}
              transition={{ duration: 0.3, ease: "easeOut" }}
            />
          </div>
          <p className="text-[11px] text-dark-muted truncate">{task.message}</p>
        </>
      )}

      {task.status === "failed" && task.error && (
        <p className="text-[11px] text-red-400 truncate" title={task.error}>
          {task.error}
        </p>
      )}

      <p className="text-[10px] text-dark-muted/60 font-mono">{task.task_id}</p>
    </motion.div>
  );
}

interface TaskProgressPanelProps {
  tasks: Record<string, TaskProgress>;
  connected: boolean;
}

export default function TaskProgressPanel({ tasks, connected }: TaskProgressPanelProps) {
  const taskList = Object.values(tasks).sort((a, b) => b.updated_at - a.updated_at);

  // 只显示最近的活跃任务（running/pending）和最近 5 个已完成的
  const active = taskList.filter((t) => t.status === "running" || t.status === "pending");
  const recent = taskList.filter((t) => t.status === "done" || t.status === "failed").slice(0, 5);
  const visible = [...active, ...recent];

  if (visible.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <span className="text-xs font-medium text-dark-muted">任务进度</span>
        <span
          className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-green-400" : "bg-red-400")}
          title={connected ? "已连接" : "未连接"}
        />
      </div>
      <AnimatePresence mode="popLayout">
        {visible.map((task) => (
          <TaskItem key={task.task_id} task={task} />
        ))}
      </AnimatePresence>
    </div>
  );
}
