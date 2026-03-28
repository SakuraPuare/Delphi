import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Progress } from "@/components/ui/Progress";
import { useBuildGraph } from "@/queries/tasks";
import { useTaskStore } from "@/stores/task-store";

interface GraphForm {
  path: string;
  include: string;
  exclude: string;
}

export function GraphTab() {
  const { t } = useTranslation();
  const { projectName } = useOutletContext<{ projectName: string }>();
  const buildGraph = useBuildGraph();
  const tasks = useTaskStore((s) => s.tasks);
  const form = useForm<GraphForm>({ defaultValues: { path: "", include: "", exclude: "" } });

  const graphTasks = [...tasks.values()].filter(
    (t) => t.task_type === "graph_build",
  );

  const onSubmit = async (data: GraphForm) => {
    try {
      await buildGraph.mutateAsync({
        project: projectName,
        path: data.path,
        include: data.include ? data.include.split(",").map((s) => s.trim()) : [],
        exclude: data.exclude ? data.exclude.split(",").map((s) => s.trim()) : [],
      });
      toast.success(t("import.importSuccess"));
      form.reset();
    } catch {
      toast.error(t("common.error"));
    }
  };

  return (
    <div className="max-w-xl space-y-6">
      <Card>
        <CardTitle className="mb-3">{t("graph.build")}</CardTitle>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm text-zinc-300">Path</label>
            <Input {...form.register("path")} placeholder="/path/to/source" />
          </div>
          <div>
            <label className="mb-1 block text-sm text-zinc-300">{t("import.include")}</label>
            <Input {...form.register("include")} placeholder="**/*.py, **/*.ts" />
          </div>
          <div>
            <label className="mb-1 block text-sm text-zinc-300">{t("import.exclude")}</label>
            <Input {...form.register("exclude")} placeholder="test/**, node_modules/**" />
          </div>
          <Button type="submit" disabled={buildGraph.isPending} className="w-full">
            {buildGraph.isPending ? t("graph.building") : t("graph.build")}
          </Button>
        </form>
      </Card>

      {graphTasks.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-zinc-300">{t("graph.status")}</h3>
          {graphTasks.map((task) => (
            <Card key={task.task_id} className="flex items-center gap-3 py-3">
              <div className="flex-1">
                <Badge
                  variant={
                    task.status === "done" ? "success" :
                    task.status === "failed" ? "error" : "default"
                  }
                >
                  {t(`task.${task.status}`)}
                </Badge>
              </div>
              {task.status === "running" && (
                <div className="w-24">
                  <Progress value={task.progress} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
