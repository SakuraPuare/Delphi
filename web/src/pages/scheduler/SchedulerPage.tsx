import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { schedulerQueryOptions, useDeleteJob, useToggleJob } from "@/queries/scheduler";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { Clock, Trash2, Power } from "lucide-react";

export function SchedulerPage() {
  const { t } = useTranslation();
  const { data: jobs, isLoading } = useQuery(schedulerQueryOptions);
  const deleteJob = useDeleteJob();
  const toggleJob = useToggleJob();

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("scheduler.title")}</h1>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : jobs && jobs.length > 0 ? (
        <div className="space-y-3">
          {jobs.map((job) => (
            <Card key={job.id} className="flex items-center gap-4">
              <Clock className="h-5 w-5 shrink-0 text-zinc-500" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-zinc-200">{job.name}</span>
                  <Badge variant={job.enabled ? "success" : "secondary"}>
                    {job.enabled ? t("scheduler.enabled") : t("scheduler.disabled")}
                  </Badge>
                </div>
                <div className="flex items-center gap-3 text-xs text-zinc-500 mt-0.5">
                  <span className="font-mono">{job.cron}</span>
                  <span>{job.task_type}</span>
                  {job.next_run && <span>Next: {job.next_run}</span>}
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => toggleJob.mutate({ id: job.id, enabled: !job.enabled })}
                >
                  <Power className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => deleteJob.mutate(job.id)}
                >
                  <Trash2 className="h-4 w-4 text-red-400" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="flex flex-col items-center justify-center py-12">
          <Clock className="h-12 w-12 text-zinc-700 mb-3" />
          <p className="text-zinc-500">{t("scheduler.noJobs")}</p>
        </Card>
      )}
    </div>
  );
}
