import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Search, ArrowRight, Clock, Brain, Shuffle, Filter, CheckCircle, Zap } from "lucide-react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { queryDebug, type QueryDebugResponse, type DebugSource } from "@/queries/pipeline";
import { cn } from "@/lib/utils";

function ScoreBar({ score, max = 1 }: { score: number; max?: number }) {
  const pct = Math.min(100, (score / max) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-full rounded-full bg-blue-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-zinc-500">{score.toFixed(3)}</span>
    </div>
  );
}

function ResultTable({ sources, showRerank }: { sources: DebugSource[]; showRerank?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-zinc-800 text-zinc-500">
            <th className="py-1.5 text-left font-medium">#</th>
            <th className="py-1.5 text-left font-medium">{t("pipeline.filePath")}</th>
            <th className="py-1.5 text-left font-medium">{t("pipeline.nodeType")}</th>
            <th className="py-1.5 text-left font-medium">{t("pipeline.vecScore")}</th>
            {showRerank && <th className="py-1.5 text-left font-medium">{t("pipeline.rerankScore")}</th>}
            <th className="py-1.5 text-left font-medium">{t("pipeline.lines")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/50">
          {sources.map((s, i) => (
            <tr key={i} className={cn("transition-colors hover:bg-zinc-800/30", s.from_graph && "bg-purple-900/10")}>
              <td className="py-1.5 text-zinc-500">{i + 1}</td>
              <td className="py-1.5 font-mono text-zinc-300">
                {s.file.split("/").pop()}
                {s.from_graph && (
                  <Badge variant="default" className="ml-1.5 text-[9px]">graph</Badge>
                )}
              </td>
              <td className="py-1.5">
                <Badge variant="secondary">{s.node_type || "—"}</Badge>
              </td>
              <td className="py-1.5"><ScoreBar score={s.vector_score} /></td>
              {showRerank && (
                <td className="py-1.5">
                  {s.rerank_score != null ? <ScoreBar score={s.rerank_score} /> : <span className="text-zinc-600">—</span>}
                </td>
              )}
              <td className="py-1.5 text-zinc-500">
                {s.start_line != null ? `${s.start_line}-${s.end_line}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface PipelineDebuggerProps {
  projectName: string;
}

export function PipelineDebugger({ projectName }: PipelineDebuggerProps) {
  const { t } = useTranslation();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryDebugResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDebug = async () => {
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await queryDebug(question, projectName);
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardTitle className="mb-3 flex items-center gap-2">
        <Zap className="h-4 w-4 text-yellow-400" />
        {t("pipeline.debugger")}
      </CardTitle>

      {/* Input */}
      <div className="mb-4 flex gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t("pipeline.debugPlaceholder")}
          onKeyDown={(e) => e.key === "Enter" && handleDebug()}
          className="flex-1"
        />
        <Button onClick={handleDebug} disabled={loading || !question.trim()}>
          <Search className="mr-1.5 h-3.5 w-3.5" />
          {loading ? t("pipeline.debugging") : t("pipeline.debug")}
        </Button>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-900/50 bg-red-900/20 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {/* Step 1: Query Rewrite */}
          <div className="flex items-start gap-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-purple-600/20 text-xs font-bold text-purple-400">1</div>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
                <Brain className="h-3.5 w-3.5" />
                {t("pipeline.queryRewrite")}
                {result.timings.rewrite_ms != null && (
                  <span className="flex items-center gap-1 text-xs text-zinc-500">
                    <Clock className="h-3 w-3" />
                    {result.timings.rewrite_ms}ms
                  </span>
                )}
              </div>
              {result.rewritten_query ? (
                <div className="mt-1 flex items-center gap-2 text-xs">
                  <span className="text-zinc-500">"{question}"</span>
                  <ArrowRight className="h-3 w-3 text-zinc-600" />
                  <span className="text-blue-400">"{result.rewritten_query}"</span>
                </div>
              ) : (
                <p className="mt-1 text-xs text-zinc-500">{t("pipeline.noRewrite")}</p>
              )}
            </div>
          </div>

          {/* Step 2: Vector Search */}
          <div className="flex items-start gap-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600/20 text-xs font-bold text-blue-400">2</div>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
                <Search className="h-3.5 w-3.5" />
                {t("pipeline.vectorSearch")}
                <Badge variant="secondary">{result.vector_results.length} results</Badge>
                {result.timings.search_ms != null && (
                  <span className="flex items-center gap-1 text-xs text-zinc-500">
                    <Clock className="h-3 w-3" />
                    {result.timings.search_ms}ms
                  </span>
                )}
              </div>
              <div className="mt-2">
                <ResultTable sources={result.vector_results} />
              </div>
            </div>
          </div>

          {/* Step 3: Reranker */}
          {result.reranked_results.length > 0 && (
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-yellow-600/20 text-xs font-bold text-yellow-400">3</div>
              <div className="flex-1">
                <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
                  <Shuffle className="h-3.5 w-3.5" />
                  {t("pipeline.reranker")}
                  <Badge variant="secondary">
                    {result.vector_results.length} → {result.reranked_results.length}
                  </Badge>
                  {result.timings.rerank_ms != null && (
                    <span className="flex items-center gap-1 text-xs text-zinc-500">
                      <Clock className="h-3 w-3" />
                      {result.timings.rerank_ms}ms
                    </span>
                  )}
                </div>
                <div className="mt-2">
                  <ResultTable sources={result.reranked_results} showRerank />
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Final Results */}
          <div className="flex items-start gap-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-600/20 text-xs font-bold text-green-400">
              {result.reranked_results.length > 0 ? 4 : 3}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
                <Filter className="h-3.5 w-3.5" />
                {t("pipeline.finalResults")}
                <Badge variant="success">{result.final_results.length} chunks</Badge>
                {result.timings.dedup_ms != null && (
                  <span className="flex items-center gap-1 text-xs text-zinc-500">
                    <Clock className="h-3 w-3" />
                    {result.timings.dedup_ms}ms
                  </span>
                )}
              </div>
              <div className="mt-2">
                <ResultTable sources={result.final_results} showRerank={result.reranked_results.length > 0} />
              </div>
            </div>
          </div>

          {/* Summary */}
          <div className="flex items-center gap-4 rounded-md border border-zinc-800 bg-zinc-900 p-3 text-xs">
            <div className="flex items-center gap-1.5">
              <CheckCircle className="h-3.5 w-3.5 text-green-400" />
              <span className="text-zinc-300">{t("pipeline.intent")}: <span className="text-blue-400">{result.intent}</span></span>
            </div>
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-zinc-500" />
              <span className="text-zinc-400">
                {t("pipeline.totalTime")}: <span className="font-mono text-zinc-200">{result.timings.total_ms}ms</span>
                {result.timings.llm_ms != null && (
                  <span className="text-zinc-600"> (LLM: {result.timings.llm_ms}ms)</span>
                )}
              </span>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
