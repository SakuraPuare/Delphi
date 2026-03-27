import { useEffect, useState } from "react";
import { fetchProjects } from "../api";
import type { ProjectInfo } from "../types";

interface Props {
  currentProject: string;
  onSelectProject: (name: string) => void;
}

export default function Sidebar({ currentProject, onSelectProject }: Props) {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProjects()
      .then(setProjects)
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <aside className="w-56 shrink-0 bg-dark-surface border-r border-dark-border flex flex-col h-full">
      <div className="p-4 border-b border-dark-border">
        <h2 className="text-sm font-semibold text-dark-muted uppercase tracking-wider">
          Projects
        </h2>
      </div>
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading && (
          <p className="text-sm text-dark-muted px-2 py-1">Loading...</p>
        )}
        {!loading && projects.length === 0 && (
          <p className="text-sm text-dark-muted px-2 py-1">No projects</p>
        )}
        {/* "All" option for querying without project filter */}
        <button
          onClick={() => onSelectProject("")}
          className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
            currentProject === ""
              ? "bg-dark-card text-white"
              : "text-dark-text hover:bg-dark-border"
          }`}
        >
          All Projects
        </button>
        {projects.map((p) => (
          <button
            key={p.name}
            onClick={() => onSelectProject(p.name)}
            className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
              currentProject === p.name
                ? "bg-dark-card text-white"
                : "text-dark-text hover:bg-dark-border"
            }`}
          >
            {p.name}
          </button>
        ))}
      </nav>
    </aside>
  );
}
