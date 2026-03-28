import { useTranslation } from "react-i18next";
import { useUIStore } from "@/stores/ui-store";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import i18n from "@/i18n";

export function SettingsPage() {
  const { t } = useTranslation();
  const { theme, setTheme } = useUIStore();

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

  return (
    <div className="mx-auto max-w-xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">{t("settings.title")}</h1>

      {/* Theme */}
      <Card>
        <CardTitle className="mb-3">{t("settings.theme")}</CardTitle>
        <div className="flex gap-2">
          {themes.map((opt) => (
            <Button
              key={opt.value}
              variant={theme === opt.value ? "default" : "outline"}
              size="sm"
              onClick={() => setTheme(opt.value)}
            >
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
            <Button
              key={opt.value}
              variant={i18n.language === opt.value ? "default" : "outline"}
              size="sm"
              onClick={() => handleLanguageChange(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </Card>
    </div>
  );
}
