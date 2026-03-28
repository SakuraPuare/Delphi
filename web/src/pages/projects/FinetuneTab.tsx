import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Progress } from "@/components/ui/Progress";
import { useGenerateFinetune } from "@/queries/tasks";
import { useTaskStore } from "@/stores/task-store";

interface FinetuneForm {
  num_samples: number;
  questions_per_chunk: number;
  format: string;
  output_path: string;
}

export function FinetuneTab() {
  const { t } = useTranslation();
  const { projectName } = useOutletContext<{ projectName: string }>();
  const generateFinetune = useGenerateFinetune();
  const tasks = useTaskStore((s) => s.tasks);
  const form = useForm<FinetuneForm>({
    defaultValues: { num_samples: 100, questions_per_chunk: 2, format: "jsonl", output_path: "" },
  });

  const finetuneTasks = [...tasks.values()].filter(
    (t) => t.task_type === "finetune_generate" || t.task_type === "finetune",
  );

  const onSubmit = async (data: FinetuneForm) => {
    try {
      await generateFinetune.mutateAsync({
        project: projectName,
        num_samples: data.num_samples,
        questions_per_chunk: data.questions_per_chunk,
        format: data.format,
        output_path: data.output_path || undefined,
      });
      toast.success(t("import.importSuccess"));
    } catch {
      toast.error(t("common.error"));
    }
  };

  return (
    <div className="max-w-xl space-y-6">
      <Card>
        <CardTitle className="mb-3">{t("finetune.generate")}</CardTitle>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm text-zinc-300">{t("finetune.numSamples")}</label>
              <Input type="number" {...form.register("num_samples")} />
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-300">{t("finetune.questionsPerChunk")}</label>
              <Input type="number" {...form.register("questions_per_chunk")} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm text-zinc-300">{t("finetune.format")}</label>
            <Input {...form.register("format")} />
          </div>
          <Button type="submit" disabled={generateFinetune.isPending} className="w-full">
            {generateFinetune.isPending ? t("finetune.generating") : t("finetune.generate")}
          </Button>
        </form>
      </Card>

      {finetuneTasks.length > 0 && (
        <div className="space-y-2">
          {finetuneTasks.map((task) => (
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
                {task.message && (
                  <p className="text-xs text-zinc-500 mt-0.5">{task.message}</p>
                )}
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
