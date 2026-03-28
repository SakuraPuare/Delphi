import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { useSuspenseQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { useUIStore } from "@/stores/ui-store";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { settingsQueryOptions, useUpdateSettings } from "@/queries/settings";
import i18n from "@/i18n";

interface SettingsForm {
  vllm_url: string;
  llm_model: string;
  llm_api_key: string;
  llm_no_think: boolean;
  embedding_backend: string;
  embedding_url: string;
  embedding_model: string;
  embedding_api_key: string;
  reranker_enabled: boolean;
  reranker_url: string;
  reranker_model: string;
  reranker_top_k: number;
  reranker_score_threshold: number;
  query_rewrite_enabled: boolean;
  retrieve_top_k: number;
  chunk_top_k: number;
  otel_enabled: boolean;
  otel_endpoint: string;
  otel_service_name: string;
}

function flatten(data: Record<string, Record<string, unknown>>): SettingsForm {
  const flat: Record<string, unknown> = {};
  for (const group of Object.values(data)) {
    Object.assign(flat, group);
  }
  return flat as unknown as SettingsForm;
}

export function SettingsPage() {
  const { t } = useTranslation();
  const { theme, setTheme } = useUIStore();
  const { data } = useSuspenseQuery(settingsQueryOptions);
  const mutation = useUpdateSettings();

  const defaults = flatten(data);
  const form = useForm<SettingsForm>({ defaultValues: defaults });

  useEffect(() => {
    form.reset(flatten(data));
  }, [data, form]);

  const onSubmit = (values: SettingsForm) => {
    // Only send changed fields; skip masked API keys
    const changed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      const orig = defaults[k as keyof SettingsForm];
      if (v !== orig && !(typeof v === "string" && v.startsWith("****"))) {
        changed[k] = v;
      }
    }
    if (Object.keys(changed).length === 0) return;
    mutation.mutate(changed, {
      onSuccess: () => toast.success(t("settings.saveSuccess")),
      onError: () => toast.error(t("settings.saveError")),
    });
  };

  const themes = [
    { value: "dark" as const, label: t("settings.dark") },
    { value: "light" as const, label: t("settings.light") },
    { value: "system" as const, label: t("settings.system") },
  ];

  const languages = [
    { value: "zh", label: "中文" },
    { value: "en", label: "English" },
  ];

  const handleLanguageChange = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem("language", lng);
  };

  const Toggle = ({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) => (
    <div className="flex items-center justify-between">
      <label className="text-sm text-zinc-300">{label}</label>
      <Button variant={checked ? "default" : "outline"} size="sm" onClick={() => onChange(!checked)}>
        {checked ? "ON" : "OFF"}
      </Button>
    </div>
  );

  const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div>
      <label className="mb-1 block text-sm text-zinc-300">{label}</label>
      {children}
    </div>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">{t("settings.title")}</h1>

      {/* Theme */}
      <Card>
        <CardTitle className="mb-3">{t("settings.theme")}</CardTitle>
        <div className="flex gap-2">
          {themes.map((opt) => (
            <Button key={opt.value} variant={theme === opt.value ? "default" : "outline"} size="sm" onClick={() => setTheme(opt.value)}>
              {opt.label}
            </Button>
          ))}
        </div>
      </Card>

      {/* Language */}
      <Card>
        <CardTitle className="mb-3">{t("settings.language")}</CardTitle>
        <div className="flex gap-2">
          {languages.map((opt) => (
            <Button key={opt.value} variant={i18n.language === opt.value ? "default" : "outline"} size="sm" onClick={() => handleLanguageChange(opt.value)}>
              {opt.label}
            </Button>
          ))}
        </div>
      </Card>

      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        {/* LLM */}
        <Card>
          <CardTitle className="mb-3">{t("settings.llm")}</CardTitle>
          <div className="space-y-3">
            <Field label={t("settings.vllmUrl")}>
              <Input {...form.register("vllm_url")} />
            </Field>
            <Field label={t("settings.llmModel")}>
              <Input {...form.register("llm_model")} />
            </Field>
            <Field label={t("settings.llmApiKey")}>
              <Input type="password" {...form.register("llm_api_key")} />
            </Field>
            <Toggle
              label={t("settings.llmNoThink")}
              checked={form.watch("llm_no_think")}
              onChange={(v) => form.setValue("llm_no_think", v, { shouldDirty: true })}
            />
          </div>
        </Card>

        {/* Embedding */}
        <Card>
          <CardTitle className="mb-3">{t("settings.embedding")}</CardTitle>
          <div className="space-y-3">
            <Field label={t("settings.embeddingBackend")}>
              <Select
                options={[
                  { value: "tei", label: "TEI" },
                  { value: "ollama", label: "Ollama" },
                  { value: "openai", label: "OpenAI" },
                  { value: "cloudflare", label: "Cloudflare" },
                ]}
                {...form.register("embedding_backend")}
              />
            </Field>
            <Field label={t("settings.embeddingUrl")}>
              <Input {...form.register("embedding_url")} />
            </Field>
            <Field label={t("settings.embeddingModel")}>
              <Input {...form.register("embedding_model")} />
            </Field>
            <Field label={t("settings.embeddingApiKey")}>
              <Input type="password" {...form.register("embedding_api_key")} />
            </Field>
          </div>
        </Card>

        {/* Reranker */}
        <Card>
          <CardTitle className="mb-3">{t("settings.reranker")}</CardTitle>
          <div className="space-y-3">
            <Toggle
              label={t("settings.rerankerEnabled")}
              checked={form.watch("reranker_enabled")}
              onChange={(v) => form.setValue("reranker_enabled", v, { shouldDirty: true })}
            />
            <Field label={t("settings.rerankerUrl")}>
              <Input {...form.register("reranker_url")} />
            </Field>
            <Field label={t("settings.rerankerModel")}>
              <Input {...form.register("reranker_model")} />
            </Field>
            <Field label={t("settings.rerankerTopK")}>
              <Input type="number" {...form.register("reranker_top_k", { valueAsNumber: true })} />
            </Field>
            <Field label={t("settings.rerankerScoreThreshold")}>
              <Input type="number" step="0.01" {...form.register("reranker_score_threshold", { valueAsNumber: true })} />
            </Field>
          </div>
        </Card>

        {/* RAG */}
        <Card>
          <CardTitle className="mb-3">{t("settings.ragParams")}</CardTitle>
          <div className="space-y-3">
            <Toggle
              label={t("settings.queryRewriteEnabled")}
              checked={form.watch("query_rewrite_enabled")}
              onChange={(v) => form.setValue("query_rewrite_enabled", v, { shouldDirty: true })}
            />
            <Field label={t("settings.retrieveTopK")}>
              <Input type="number" {...form.register("retrieve_top_k", { valueAsNumber: true })} />
            </Field>
            <Field label={t("settings.chunkTopK")}>
              <Input type="number" {...form.register("chunk_top_k", { valueAsNumber: true })} />
            </Field>
          </div>
        </Card>

        {/* Observability */}
        <Card>
          <CardTitle className="mb-3">{t("settings.observability")}</CardTitle>
          <div className="space-y-3">
            <Toggle
              label={t("settings.otelEnabled")}
              checked={form.watch("otel_enabled")}
              onChange={(v) => form.setValue("otel_enabled", v, { shouldDirty: true })}
            />
            <Field label={t("settings.otelEndpoint")}>
              <Input {...form.register("otel_endpoint")} />
            </Field>
            <Field label={t("settings.otelServiceName")}>
              <Input {...form.register("otel_service_name")} />
            </Field>
          </div>
        </Card>

        <Button type="submit" disabled={mutation.isPending} className="w-full">
          {mutation.isPending ? t("common.loading") : t("settings.save")}
        </Button>
      </form>
    </div>
  );
}