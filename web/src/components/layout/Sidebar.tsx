import { NavLink } from "react-router";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  FolderOpen,
  MessageSquare,
  Clock,
  Box,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";
import { useTaskStore } from "@/stores/task-store";
import { Progress } from "@/components/ui/Progress";

const navItems = [
  { to: "/", icon: LayoutDashboard, labelKey: "nav.dashboard" },
  { to: "/projects", icon: FolderOpen, labelKey: "nav.projects" },
  { to: "/chat", icon: MessageSquare, labelKey: "nav.chat" },
  { to: "/scheduler", icon: Clock, labelKey: "nav.scheduler" },
  { to: "/models", icon: Box, labelKey: "nav.models" },
];

export function Sidebar() {
  const { t } = useTranslation();
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const tasks = useTaskStore((s) => s.tasks);

  const activeTasks = [...tasks.values()].filter(
    (t) => t.status === "pending" || t.status === "running",
  );

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r border-zinc-800 bg-zinc-950 transition-all duration-200",
        sidebarOpen ? "w-56" : "w-14",
      )}
    >
      {/* Logo + Toggle */}
      <div className="flex h-14 items-center justify-between px-3">
        {sidebarOpen && (
          <span className="text-lg font-bold text-zinc-100">Delphi</span>
        )}
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
        >
          {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-2">
        {navItems.map(({ to, icon: Icon, labelKey }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-zinc-800 text-zinc-100"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200",
                !sidebarOpen && "justify-center",
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {sidebarOpen && <span>{t(labelKey)}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Active Tasks */}
      {activeTasks.length > 0 && sidebarOpen && (
        <div className="border-t border-zinc-800 px-3 py-3">
          <p className="mb-2 text-xs font-medium text-zinc-500">
            {t("task.progress")} ({activeTasks.length})
          </p>
          <div className="space-y-2">
            {activeTasks.slice(0, 3).map((task) => (
              <div key={task.task_id}>
                <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
                  <span className="truncate">{task.task_type || task.task_id.slice(0, 8)}</span>
                  <span>{Math.round(task.progress)}%</span>
                </div>
                <Progress value={task.progress} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Version */}
      {sidebarOpen && (
        <div className="border-t border-zinc-800 px-3 py-2">
          <span className="text-xs text-zinc-600">v0.1.0</span>
        </div>
      )}
    </aside>
  );
}
