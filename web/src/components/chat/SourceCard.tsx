import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, FileCode, ExternalLink, FolderOpen } from "lucide-react";
import * as Collapsible from "@radix-ui/react-collapsible";
import { cn } from "@/lib/utils";
import type { Source } from "@/types";

interface SourceCardProps {
  sources: Source[];
}

/** 将 git clone URL 转为 GitHub blob 浏览链接 */
function buildGitHubUrl(repoUrl: string, file: string, startLine?: number, endLine?: number): string | null {
  // 支持 https://github.com/user/repo.git 和 https://github.com/user/repo
  const m = repoUrl.match(/github\.com[/:]([^/]+\/[^/]+?)(?:\.git)?$/);
  if (!m) return null;
  const repo = m[1];
  let url = `https://github.com/${repo}/blob/main/${file}`;
  if (startLine != null) {
    url += `#L${startLine}`;
    if (endLine != null && endLine !== startLine) {
      url += `-L${endLine}`;
    }
  }
  return url;
}

function isGitHubSource(repoUrl?: string): boolean {
  return !!repoUrl && repoUrl.includes("github.com");
}

export function SourceCard({ sources }: SourceCardProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="mt-2">
      <Collapsible.Trigger className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
        <FileCode className="h-3 w-3" />
        {t("chat.sources")} ({sources.length})
        <ChevronDown
          className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
        />
      </Collapsible.Trigger>
      <Collapsible.Content className="mt-2 space-y-1.5">
        {sources.map((src, i) => {
          const ghUrl = src.repo_url ? buildGitHubUrl(src.repo_url, src.file, src.start_line, src.end_line) : null;
          const isGh = isGitHubSource(src.repo_url);

          return (
            <div
              key={i}
              className="rounded-md border border-zinc-800 bg-zinc-900 p-2 text-xs"
            >
              <div className="flex items-center justify-between mb-1 gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  {isGh ? (
                    <svg className="h-3.5 w-3.5 shrink-0 text-zinc-400" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                    </svg>
                  ) : (
                    <FolderOpen className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
                  )}
                  {ghUrl ? (
                    <a
                      href={ghUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-blue-400 hover:text-blue-300 hover:underline truncate"
                      title={src.file}
                    >
                      {src.file}
                    </a>
                  ) : (
                    <span className="font-mono text-zinc-300 truncate" title={src.file}>
                      {src.file}
                    </span>
                  )}
                  {ghUrl && (
                    <a
                      href={ghUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-zinc-500 hover:text-blue-400"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {src.start_line != null && (
                    <span className="text-zinc-600">
                      L{src.start_line}
                      {src.end_line != null && src.end_line !== src.start_line && `-${src.end_line}`}
                    </span>
                  )}
                </div>
              </div>
              {/* 来源标签 */}
              <div className="flex items-center gap-1.5 mb-1">
                {isGh ? (
                  <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-zinc-800 text-zinc-400">
                    GitHub
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-zinc-800 text-zinc-400">
                    {t("chat.sourceLocal")}
                  </span>
                )}
              </div>
              {src.chunk && (
                <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-zinc-500">
                  {src.chunk}
                </pre>
              )}
            </div>
          );
        })}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
