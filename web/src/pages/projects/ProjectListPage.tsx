import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Plus, FolderOpen, Trash2 } from "lucide-react";
import { projectsQueryOptions, useDeleteProject } from "@/queries/projects";
import { Card, CardContent, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { useState } from "react";
import { toast } from "sonner";

export function ProjectListPage() {
  const { t } = useTranslation();
  const { data: projects, isLoading } = useQuery(projectsQueryOptions);
  const deleteProject = useDeleteProject();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteProject.mutateAsync(deleteTarget);
      toast.success(t("project.deleteSuccess"));
    } catch {
      toast.error(t("common.error"));
    }
    setDeleteTarget(null);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("project.title")}</h1>
        <Link to="/projects/new">
          <Button>
            <Plus className="h-4 w-4" />
            {t("project.create")}
          </Button>
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Card key={p.name} className="group relative transition-colors hover:border-zinc-700">
              <Link to={`/projects/${p.name}`} className="block">
                <CardTitle className="text-base">{p.name}</CardTitle>
                <CardContent>
                  {p.description && (
                    <p className="mb-2 line-clamp-2">{p.description}</p>
                  )}
                  <div className="flex items-center gap-3 text-xs text-zinc-500">
                    <Badge variant="secondary">{p.chunk_count.toLocaleString()} chunks</Badge>
                    {p.created_at && (
                      <span>{new Date(p.created_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </CardContent>
              </Link>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  setDeleteTarget(p.name);
                }}
                className="absolute right-3 top-3 rounded-md p-1 text-zinc-600 opacity-0 transition-opacity hover:bg-zinc-800 hover:text-red-400 group-hover:opacity-100"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </Card>
          ))}
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("common.confirm")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-zinc-400 mb-4">
            {t("project.deleteConfirm", { name: deleteTarget })}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteProject.isPending}
            >
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
