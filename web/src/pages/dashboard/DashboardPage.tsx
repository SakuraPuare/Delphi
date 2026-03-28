import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Plus, FolderOpen, MessageSquare, Activity } from "lucide-react";
import { projectsQueryOptions } from "@/queries/projects";
import { healthQueryOptions } from "@/queries/health";
import { Card, CardContent, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";

export function DashboardPage() {
  const { t } = useTranslation();
  const { data: projects, isLoading: loadingProjects } = useQuery(projectsQueryOptions);
  const { data: status } = useQuery(healthQueryOptions);

  return (
    <div className="mx-auto max-w-6xl space-y-8 p-6">
      {/* Quick Actions */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
        <div className="flex gap-2">
          <Link to="/projects/new">
            <Button>
              <Plus className="h-4 w-4" />
              {t("dashboard.newProject")}
            </Button>
          </Link>
          <Link to="/chat">
            <Button variant="secondary">
              <MessageSquare className="h-4 w-4" />
              {t("dashboard.startChat")}
            </Button>
          </Link>
        </div>
      </div>

      {/* System Status */}
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Activity className="h-4 w-4 text-zinc-400" />
          <CardTitle>{t("dashboard.systemStatus")}</CardTitle>
        </div>
        <CardContent>
          {status ? (
            <div className="grid grid-cols-3 gap-4">
              {(["vllm", "qdrant", "embedding"] as const).map((svc) => (
                <div key={svc} className="flex items-center justify-between rounded-md border border-zinc-800 p-3">
                  <div>
                    <p className="text-sm font-medium text-zinc-200">{t(`status.${svc}`)}</p>
                    {status[svc].model && (
                      <p className="text-xs text-zinc-500 mt-0.5">{status[svc].model}</p>
                    )}
                  </div>
                  <Badge variant={status[svc].ok ? "success" : "error"}>
                    {status[svc].ok ? t("status.healthy") : t("status.unhealthy")}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Projects Grid */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <FolderOpen className="h-4 w-4 text-zinc-400" />
          <h2 className="text-lg font-semibold">{t("nav.projects")}</h2>
          {projects && (
            <Badge variant="secondary">{projects.length}</Badge>
          )}
        </div>

        {loadingProjects ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        ) : projects && projects.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <Link key={p.name} to={`/projects/${p.name}`}>
                <Card className="transition-colors hover:border-zinc-700 cursor-pointer h-full">
                  <CardTitle className="text-base">{p.name}</CardTitle>
                  <CardContent>
                    {p.description && (
                      <p className="mb-2 line-clamp-2">{p.description}</p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-zinc-500">
                      <span>{p.chunk_count.toLocaleString()} chunks</span>
                      {p.created_at && (
                        <span>{new Date(p.created_at).toLocaleDateString()}</span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
            {/* New project card */}
            <Link to="/projects/new">
              <Card className="flex h-full items-center justify-center border-dashed transition-colors hover:border-zinc-600 cursor-pointer min-h-[120px]">
                <div className="text-center text-zinc-500">
                  <Plus className="mx-auto h-8 w-8 mb-1" />
                  <span className="text-sm">{t("project.create")}</span>
                </div>
              </Card>
            </Link>
          </div>
        ) : (
          <Card className="flex flex-col items-center justify-center py-12">
            <FolderOpen className="h-12 w-12 text-zinc-700 mb-3" />
            <p className="text-zinc-500 mb-4">{t("common.noData")}</p>
            <Link to="/projects/new">
              <Button>
                <Plus className="h-4 w-4" />
                {t("project.create")}
              </Button>
            </Link>
          </Card>
        )}
      </div>
    </div>
  );
}
