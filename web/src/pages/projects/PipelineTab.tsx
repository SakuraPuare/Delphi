import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { projectStatsOptions } from "@/queries/pipeline";
import { StatsCharts } from "@/components/project/StatsCharts";
import { ChunkBrowser } from "@/components/project/ChunkBrowser";
import { PipelineDebugger } from "@/components/project/PipelineDebugger";
import { Badge } from "@/components/ui/Badge";

export function PipelineTab() {
  const { t } = useTranslation();
  const { projectName } = useOutletContext<{ projectName: string }>();
  const { data: stats, isLoading: statsLoading } = useQuery(projectStatsOptions(projectName));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Database className="h-5 w-5 text-zinc-400" />
        <h2 className="text-lg font-semibold">{t("pipeline.title")}</h2>
        {stats && (
          <Badge variant="secondary">{stats.total_chunks.toLocaleString()} chunks</Badge>
        )}
      </div>

      {/* Stats Charts */}
      <StatsCharts stats={stats} isLoading={statsLoading} />

      {/* Chunk Browser */}
      <ChunkBrowser projectName={projectName} stats={stats} />

      {/* Pipeline Debugger */}
      <PipelineDebugger projectName={projectName} />
    </div>
  );
}
