import { useTranslation } from "react-i18next";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Card, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { ProjectStats } from "@/queries/pipeline";

const COLORS = [
  "#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#64748b",
];

interface StatsChartsProps {
  stats: ProjectStats | undefined;
  isLoading: boolean;
}

export function StatsCharts({ stats, isLoading }: StatsChartsProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-64" />)}
      </div>
    );
  }

  if (!stats) return null;

  const langData = Object.entries(stats.by_language)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));

  const typeData = Object.entries(stats.by_node_type)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));

  const fileData = stats.top_files.slice(0, 10).map((f) => ({
    name: f.file_path.split("/").pop() || f.file_path,
    fullPath: f.file_path,
    count: f.count,
  }));

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* Language Distribution */}
      <Card>
        <CardTitle className="mb-3">{t("pipeline.byLanguage")}</CardTitle>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={langData}
              cx="50%"
              cy="50%"
              innerRadius={40}
              outerRadius={70}
              dataKey="value"
              label={({ name, percent }: { name?: string; percent?: number }) => `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`}
              labelLine={false}
              fontSize={11}
            >
              {langData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </Card>

      {/* Node Type Distribution */}
      <Card>
        <CardTitle className="mb-3">{t("pipeline.byType")}</CardTitle>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={typeData}
              cx="50%"
              cy="50%"
              innerRadius={40}
              outerRadius={70}
              dataKey="value"
              label={({ name, percent }: { name?: string; percent?: number }) => `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`}
              labelLine={false}
              fontSize={11}
            >
              {typeData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </Card>

      {/* Top Files */}
      <Card>
        <CardTitle className="mb-3">{t("pipeline.topFiles")}</CardTitle>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={fileData} layout="vertical" margin={{ left: 0, right: 10 }}>
            <XAxis type="number" fontSize={10} />
            <YAxis type="category" dataKey="name" width={100} fontSize={10} />
            <Tooltip />
            <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
