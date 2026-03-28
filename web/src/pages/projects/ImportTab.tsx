import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { GitBranch, FileText, Film } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Progress } from "@/components/ui/Progress";
import { Badge } from "@/components/ui/Badge";
import { useImportGit, useImportDocs, useImportMedia } from "@/queries/tasks";
import { useTaskStore } from "@/stores/task-store";

interface GitForm {
  url: string;
  branch: string;
  include: string;
  exclude: string;
  depth: number;
}

interface DocForm {
  path: string;
  file_types: string;
  recursive: boolean;
}

interface MediaForm {
  path: string;
  whisper_model: string;
  recursive: boolean;
}

export function ImportTab() {
  const { t } = useTranslation();
  const { projectName } = useOutletContext<{ projectName: string }>();
  const importGit = useImportGit();
  const importDocs = useImportDocs();
  const importMedia = useImportMedia();
  const tasks = useTaskStore((s) => s.tasks);
  const [activeTab, setActiveTab] = useState("git");

  const gitForm = useForm<GitForm>({ defaultValues: { branch: "main", depth: 1, include: "", exclude: "" } });
  const docForm = useForm<DocForm>({ defaultValues: { file_types: "md,txt,pdf,html", recursive: true } });
  const mediaForm = useForm<MediaForm>({ defaultValues: { whisper_model: "large-v3", recursive: true } });

  const onGitSubmit = async (data: GitForm) => {
    try {
      await importGit.mutateAsync({
        url: data.url,
        project: projectName,
        branch: data.branch,
        include: data.include ? data.include.split(",").map((s) => s.trim()) : [],
        exclude: data.exclude ? data.exclude.split(",").map((s) => s.trim()) : [],
        depth: data.depth,
      });
      toast.success(t("import.importSuccess"));
      gitForm.reset();
    } catch {
      toast.error(t("common.error"));
    }
  };

  const onDocSubmit = async (data: DocForm) => {
    try {
      await importDocs.mutateAsync({
        path: data.path,
        project: projectName,
        file_types: data.file_types.split(",").map((s) => s.trim()),
        recursive: data.recursive,
      });
      toast.success(t("import.importSuccess"));
      docForm.reset();
    } catch {
      toast.error(t("common.error"));
    }
  };

  const onMediaSubmit = async (data: MediaForm) => {
    try {
      await importMedia.mutateAsync({
        path: data.path,
        project: projectName,
        whisper_model: data.whisper_model,
        recursive: data.recursive,
      });
      toast.success(t("import.importSuccess"));
      mediaForm.reset();
    } catch {
      toast.error(t("common.error"));
    }
  };

  const taskList = [...tasks.values()].filter(
    (t) => t.metadata?.project === projectName || t.task_type?.includes("import"),
  );

  return (
    <div className="space-y-6">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="git">
            <GitBranch className="mr-1.5 h-3.5 w-3.5" />
            {t("import.git")}
          </TabsTrigger>
          <TabsTrigger value="docs">
            <FileText className="mr-1.5 h-3.5 w-3.5" />
            {t("import.docs")}
          </TabsTrigger>
          <TabsTrigger value="media">
            <Film className="mr-1.5 h-3.5 w-3.5" />
            {t("import.media")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="git">
          <Card>
            <form onSubmit={gitForm.handleSubmit(onGitSubmit)} className="space-y-3">
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.repoUrl")}</label>
                <Input {...gitForm.register("url")} placeholder="https://github.com/user/repo" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm text-zinc-300">{t("import.branch")}</label>
                  <Input {...gitForm.register("branch")} />
                </div>
                <div>
                  <label className="mb-1 block text-sm text-zinc-300">Depth</label>
                  <Input type="number" {...gitForm.register("depth")} />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.include")}</label>
                <Input {...gitForm.register("include")} placeholder="src/**, docs/**" />
              </div>
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.exclude")}</label>
                <Input {...gitForm.register("exclude")} placeholder="node_modules/**, .git/**" />
              </div>
              <Button type="submit" disabled={importGit.isPending} className="w-full">
                {t("import.startImport")}
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="docs">
          <Card>
            <form onSubmit={docForm.handleSubmit(onDocSubmit)} className="space-y-3">
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.docPath")}</label>
                <Input {...docForm.register("path")} placeholder="/path/to/documents" />
              </div>
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.fileTypes")}</label>
                <Input {...docForm.register("file_types")} />
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input type="checkbox" {...docForm.register("recursive")} className="rounded" />
                {t("import.recursive")}
              </label>
              <Button type="submit" disabled={importDocs.isPending} className="w-full">
                {t("import.startImport")}
              </Button>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="media">
          <Card>
            <form onSubmit={mediaForm.handleSubmit(onMediaSubmit)} className="space-y-3">
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.mediaPath")}</label>
                <Input {...mediaForm.register("path")} placeholder="/path/to/media" />
              </div>
              <div>
                <label className="mb-1 block text-sm text-zinc-300">{t("import.whisperModel")}</label>
                <Input {...mediaForm.register("whisper_model")} />
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input type="checkbox" {...mediaForm.register("recursive")} className="rounded" />
                {t("import.recursive")}
              </label>
              <Button type="submit" disabled={importMedia.isPending} className="w-full">
                {t("import.startImport")}
              </Button>
            </form>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Import History / Active Tasks */}
      {taskList.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-medium text-zinc-300">{t("import.history")}</h3>
          <div className="space-y-2">
            {taskList.map((task) => (
              <Card key={task.task_id} className="flex items-center gap-3 py-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-zinc-200 truncate">
                      {task.task_type || "import"}
                    </span>
                    <Badge
                      variant={
                        task.status === "done" ? "success" :
                        task.status === "failed" ? "error" :
                        task.status === "running" ? "default" : "secondary"
                      }
                    >
                      {t(`task.${task.status}`)}
                    </Badge>
                  </div>
                  {task.message && (
                    <p className="text-xs text-zinc-500 mt-0.5 truncate">{task.message}</p>
                  )}
                </div>
                {(task.status === "running" || task.status === "pending") && (
                  <div className="w-24">
                    <Progress value={task.progress} />
                  </div>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
