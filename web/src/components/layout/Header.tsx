import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Settings, Menu } from "lucide-react";
import { Link, useMatches } from "react-router";
import { healthQueryOptions } from "@/queries/health";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        ok ? "bg-green-500" : "bg-red-500",
      )}
    />
  );
}

export function Header() {
  const { t } = useTranslation();
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const { data: status } = useQuery(healthQueryOptions);

  const matches = useMatches();
  const crumbs = matches
    .filter((m) => (m.handle as { crumb?: string })?.crumb)
    .map((m) => ({
      label: (m.handle as { crumb: string }).crumb,
      path: m.pathname,
    }));

  return (
    <header className="flex h-14 items-center justify-between border-b border-zinc-800 bg-zinc-950 px-4">
      <div className="flex items-center gap-3">
        {!sidebarOpen && (
          <button
            onClick={toggleSidebar}
            className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 md:hidden"
          >
            <Menu className="h-4 w-4" />
          </button>
        )}
        {/* Breadcrumbs */}
        <nav className="flex items-center gap-1.5 text-sm text-zinc-400">
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex items-center gap-1.5">
              {i > 0 && <span>/</span>}
              <Link to={c.path} className="hover:text-zinc-200">
                {c.label}
              </Link>
            </span>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-4">
        {/* System Status */}
        {status && (
          <div className="flex items-center gap-3 text-xs text-zinc-400">
            <span className="flex items-center gap-1.5">
              <StatusDot ok={status.vllm.ok} />
              {t("status.vllm")}
            </span>
            <span className="flex items-center gap-1.5">
              <StatusDot ok={status.qdrant.ok} />
              {t("status.qdrant")}
            </span>
            <span className="flex items-center gap-1.5">
              <StatusDot ok={status.embedding.ok} />
              {t("status.embedding")}
            </span>
          </div>
        )}

        <Link
          to="/settings"
          className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
        >
          <Settings className="h-4 w-4" />
        </Link>
      </div>
    </header>
  );
}
