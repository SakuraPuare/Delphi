import { Menu, Settings } from "lucide-react";
import { useStore } from "@/store";
import { cn } from "@/lib/utils";

export default function Header() {
  const currentProject = useStore((s) => s.currentProject);
  const toggleSidebar = useStore((s) => s.toggleSidebar);

  return (
    <header className="flex h-12 shrink-0 items-center border-b border-dark-border bg-dark-surface px-4">
      <button
        onClick={toggleSidebar}
        className={cn(
          "mr-3 rounded-md p-1.5 text-dark-muted transition-colors hover:bg-dark-hover hover:text-dark-text",
          "md:hidden",
        )}
        aria-label="Toggle sidebar"
      >
        <Menu className="h-5 w-5" />
      </button>

      <h1 className="text-lg font-semibold tracking-wide">Delphi</h1>
      {currentProject && (
        <span className="ml-3 text-sm text-dark-muted">/ {currentProject}</span>
      )}

      <div className="flex-1" />

      <button
        className="rounded-md p-1.5 text-dark-muted transition-colors hover:bg-dark-hover hover:text-dark-text"
        aria-label="Settings"
      >
        <Settings className="h-5 w-5" />
      </button>
    </header>
  );
}
