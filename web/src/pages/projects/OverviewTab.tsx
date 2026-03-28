import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router";
import { Database, FileText, Clock } from "lucide-react";
import { Card, CardContent, CardTitle } from "@/components/ui/Card";
import type { ProjectInfo } from "@/types";

export function OverviewTab() {
  const { t } = useTranslation();
  const { project } = useOutletContext<{ projectName: string; project?: ProjectInfo }>();

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-blue-600/20 p-2">
              <Database className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold">{project?.chunk_count.toLocaleString() ?? 0}</p>
              <p className="text-xs text-zinc-500">{t("project.chunks")}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-green-600/20 p-2">
              <FileText className="h-5 w-5 text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-bold">—</p>
              <p className="text-xs text-zinc-500">{t("project.dataSources")}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-purple-600/20 p-2">
              <Clock className="h-5 w-5 text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {project?.created_at ? new Date(project.created_at).toLocaleDateString() : "—"}
              </p>
              <p className="text-xs text-zinc-500">{t("project.recentActivity")}</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Description */}
      {project?.description && (
        <Card>
          <CardTitle>{t("project.description")}</CardTitle>
          <CardContent className="mt-2">{project.description}</CardContent>
        </Card>
      )}
    </div>
  );
}
