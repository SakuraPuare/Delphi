import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { useCreateProject } from "@/queries/projects";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { Link } from "react-router";

export function ProjectNewPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const createProject = useCreateProject();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createProject.mutateAsync({ name: name.trim(), description: description.trim() });
      toast.success(t("project.createSuccess"));
      navigate(`/projects/${name.trim()}/import`);
    } catch {
      toast.error(t("common.error"));
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Link to="/projects" className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="text-2xl font-bold">{t("project.create")}</h1>
      </div>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">
              {t("project.name")}
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("project.namePlaceholder")}
              required
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-zinc-300">
              {t("project.description")}
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("project.descriptionPlaceholder")}
              rows={3}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Link to="/projects">
              <Button type="button" variant="ghost">{t("common.cancel")}</Button>
            </Link>
            <Button type="submit" disabled={!name.trim() || createProject.isPending}>
              {t("common.create")}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
