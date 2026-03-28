import { NavLink, Outlet, useParams, Link } from "react-router";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, Download, MessageSquare, Database, GitBranch, Sparkles, Settings } from "lucide-react";
import { projectsQueryOptions } from "@/queries/projects";
import { cn } from "@/lib/utils";

const tabs = [
  { path: "overview", icon: BarChart3, labelKey: "project.overview" },
  { path: "import", icon: Download, labelKey: "project.import" },
  { path: "chat", icon: MessageSquare, labelKey: "project.chat" },
  { path: "pipeline", icon: Database, labelKey: "project.pipeline" },
  { path: "graph", icon: GitBranch, labelKey: "project.graph" },
  { path: "finetune", icon: Sparkles, labelKey: "project.finetune" },
  { path: "settings", icon: Settings, labelKey: "project.settings" },
];

export function ProjectLayout() {
  const { t } = useTranslation();
  const { name } = useParams<{ name: string }>();
  const { data: projects } = useQuery(projectsQueryOptions);
  const project = projects?.find((p) => p.name === name);

  return (
    <div className="flex h-full flex-col">
      {/* Project Header */}
      <div className="border-b border-zinc-800 px-6 pt-4 pb-0">
        <div className="flex items-center gap-3 mb-3">
          <Link to="/projects" className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-xl font-bold">{name}</h1>
          {project?.description && (
            <span className="text-sm text-zinc-500">{project.description}</span>
          )}
        </div>

        {/* Tab Navigation */}
        <nav className="flex gap-1">
          {tabs.map(({ path, icon: Icon, labelKey }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "overview"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "border-blue-500 text-zinc-100"
                    : "border-transparent text-zinc-400 hover:text-zinc-200",
                )
              }
            >
              <Icon className="h-3.5 w-3.5" />
              {t(labelKey)}
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto p-6">
        <Outlet context={{ projectName: name, project }} />
      </div>
    </div>
  );
}
