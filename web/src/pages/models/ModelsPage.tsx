import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { modelsQueryOptions, useActivateModel } from "@/queries/models";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { Box, Power } from "lucide-react";

export function ModelsPage() {
  const { t } = useTranslation();
  const { data: models, isLoading } = useQuery(modelsQueryOptions);
  const activateModel = useActivateModel();

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("models.title")}</h1>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : models && models.length > 0 ? (
        <div className="space-y-3">
          {models.map((model) => (
            <Card key={model.name} className="flex items-center gap-4">
              <Box className="h-5 w-5 shrink-0 text-zinc-500" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-zinc-200">{model.name}</span>
                  <Badge variant={model.active ? "success" : "secondary"}>
                    {model.active ? t("models.active") : t("models.inactive")}
                  </Badge>
                  <Badge variant="secondary">{model.model_type}</Badge>
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  {model.model_path}
                  {model.description && ` — ${model.description}`}
                </div>
              </div>
              {!model.active && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => activateModel.mutate(model.name)}
                  disabled={activateModel.isPending}
                >
                  <Power className="h-4 w-4 mr-1" />
                  {t("models.activate")}
                </Button>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <Card className="flex flex-col items-center justify-center py-12">
          <Box className="h-12 w-12 text-zinc-700 mb-3" />
          <p className="text-zinc-500">{t("common.noData")}</p>
        </Card>
      )}
    </div>
  );
}
