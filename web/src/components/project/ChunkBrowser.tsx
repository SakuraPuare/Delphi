import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Search, ChevronDown, FileCode } from "lucide-react";
import { projectChunksOptions, type ChunkDetail } from "@/queries/pipeline";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { Select } from "@/components/ui/Select";
import type { ProjectStats } from "@/queries/pipeline";

interface ChunkBrowserProps {
  projectName: string;
  stats: ProjectStats | undefined;
}

export function ChunkBrowser({ projectName, stats }: ChunkBrowserProps) {
  const { t } = useTranslation();
  const [language, setLanguage] = useState("");
  const [nodeType, setNodeType] = useState("");
  const [filePath, setFilePath] = useState("");
  const [offset, setOffset] = useState<string | undefined>();
  const [allChunks, setAllChunks] = useState<ChunkDetail[]>([]);

  const { data, isLoading } = useQuery({
    ...projectChunksOptions(projectName, {
      limit: 50,
      offset,
      language: language || undefined,
      node_type: nodeType || undefined,
      file_path: filePath || undefined,
    }),
    placeholderData: (prev) => prev,
  });

  // Merge loaded chunks
  const displayChunks = offset ? [...allChunks, ...(data?.chunks || [])] : (data?.chunks || []);

  const languageOptions = stats
    ? [{ value: "", label: t("pipeline.allLanguages") }, ...Object.keys(stats.by_language).map((l) => ({ value: l, label: l }))]
    : [{ value: "", label: t("pipeline.allLanguages") }];

  const typeOptions = stats
    ? [{ value: "", label: t("pipeline.allTypes") }, ...Object.keys(stats.by_node_type).map((t) => ({ value: t, label: t }))]
    : [{ value: "", label: t("pipeline.allTypes") }];

  const handleFilterChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLSelectElement>) => {
    setter(e.target.value);
    setOffset(undefined);
    setAllChunks([]);
  };

  const handleLoadMore = () => {
    if (data?.next_offset) {
      setAllChunks(displayChunks);
      setOffset(data.next_offset);
    }
  };

  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <FileCode className="h-4 w-4 text-zinc-400" />
        <span className="text-sm font-medium text-zinc-200">{t("pipeline.chunkBrowser")}</span>
        {data && (
          <Badge variant="secondary">{data.total} chunks</Badge>
        )}
        <div className="flex-1" />
        <Select options={languageOptions} value={language} onChange={handleFilterChange(setLanguage)} className="w-32" />
        <Select options={typeOptions} value={nodeType} onChange={handleFilterChange(setNodeType)} className="w-32" />
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            value={filePath}
            onChange={(e) => {
              setFilePath(e.target.value);
              setOffset(undefined);
              setAllChunks([]);
            }}
            placeholder={t("pipeline.filterByFile")}
            className="w-48 rounded-md border border-zinc-700 bg-zinc-900 py-1.5 pl-7 pr-2 text-xs text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      </div>

      {isLoading && !data ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-10" />)}
        </div>
      ) : (
        <>
          {/* Table Header */}
          <div className="grid grid-cols-[1fr_100px_120px_80px] gap-2 border-b border-zinc-800 pb-2 text-xs font-medium text-zinc-500">
            <span>{t("pipeline.filePath")}</span>
            <span>{t("pipeline.nodeType")}</span>
            <span>{t("pipeline.symbol")}</span>
            <span>{t("pipeline.lines")}</span>
          </div>

          {/* Rows */}
          <div className="divide-y divide-zinc-800/50">
            {displayChunks.map((chunk) => (
              <div key={chunk.id}>
                <button
                  onClick={() => setExpandedId(expandedId === chunk.id ? null : chunk.id)}
                  className="grid w-full grid-cols-[1fr_100px_120px_80px] gap-2 py-2 text-left text-xs transition-colors hover:bg-zinc-800/30"
                >
                  <span className="truncate font-mono text-zinc-300">{chunk.file_path}</span>
                  <Badge variant="secondary" className="w-fit">{chunk.node_type || "—"}</Badge>
                  <span className="truncate text-zinc-400">{chunk.symbol_name || "—"}</span>
                  <span className="text-zinc-500">
                    {chunk.start_line}-{chunk.end_line}
                  </span>
                </button>
                {expandedId === chunk.id && (
                  <div className="mb-2 rounded-md bg-zinc-900 p-3">
                    <div className="mb-1 flex items-center gap-2 text-[10px] text-zinc-500">
                      <Badge variant="secondary">{chunk.language}</Badge>
                      {chunk.parent_symbol && <span>parent: {chunk.parent_symbol}</span>}
                    </div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-zinc-400">
                      {chunk.text_preview}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Load More */}
          {data?.next_offset && (
            <div className="mt-3 text-center">
              <Button variant="ghost" size="sm" onClick={handleLoadMore} disabled={isLoading}>
                <ChevronDown className="mr-1 h-3.5 w-3.5" />
                {t("pipeline.loadMore")}
              </Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
