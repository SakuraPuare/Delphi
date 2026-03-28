import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useOutletContext, useNavigate } from "react-router";
import { useDeleteProject } from "@/queries/projects";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { toast } from "sonner";
import type { ProjectInfo } from "@/types";

export function ProjectSettingsTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { projectName, project } = useOutletContext<{ projectName: string; project?: ProjectInfo }>();
  const deleteProject = useDeleteProject();
  const [confirmName, setConfirmName] = useState("");

  const handleDelete = async () => {
    if (confirmName !== projectName) return;
    try {
      await deleteProject.mutateAsync(projectName);
      toast.success(t("project.deleteSuccess"));
      navigate("/projects");
    } catch {
      toast.error(t("common.error"));
    }
  };

  return (
    <div className="max-w-xl space-y-6">
      {/* Project Info */}
      <Card>
        <CardTitle className="mb-3">{t("project.settings")}</CardTitle>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm text-zinc-300">{t("project.name")}</label>
            <Input value={projectName} disabled />
          </div>
          <div>
            <label className="mb-1 block text-sm text-zinc-300">{t("project.description")}</label>
            <Textarea defaultValue={project?.description ?? ""} disabled />
          </div>
        </div>
      </Card>

      {/* Danger Zone */}
      <Card className="border-red-900/50">
        <CardTitle className="text-red-400 mb-3">{t("common.delete")}</CardTitle>
        <p className="text-sm text-zinc-400 mb-3">
          {t("project.deleteConfirm", { name: projectName })}
        </p>
        <div className="space-y-3">
          <Input
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder={projectName}
          />
          <Button
            variant="destructive"
            disabled={confirmName !== projectName || deleteProject.isPending}
            onClick={handleDelete}
          >
            {t("common.delete")}
          </Button>
        </div>
      </Card>
    </div>
  );
}
