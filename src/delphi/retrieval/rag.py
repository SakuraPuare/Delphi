from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from delphi.core.config import settings
from delphi.core.telemetry import get_tracer
from delphi.retrieval.intent import classify_intent, get_system_prompt

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.graph.store import GraphStore

from loguru import logger

_tracer = get_tracer(__name__)

SYSTEM_PROMPT = (
    "你是一个代码与文档问答助手。请根据以下检索到的上下文内容回答用户的问题。\n\n"
    "规则：\n"
    "- 只基于提供的上下文回答，不要编造信息\n"
    '- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"\n'
    "- 在回答中引用来源时，使用格式 [[来源: 文件路径, 行 X-Y]] 标注\n"
    "- 每个关键论述都应附带来源引用\n"
    "- 代码示例使用代码块格式，并标注来源文件"
)


@dataclass
class ScoredChunk:
    content: str
    file_path: str
    start_line: int | None
    end_line: int | None
    score: float
    vector_score: float = 0.0
    from_graph: bool = False
    node_type: str = ""
    language: str = ""
    repo_url: str = ""


class RerankerClient:
    """TEI Reranker 服务客户端"""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.reranker_url).rstrip("/")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def rerank(self, query: str, texts: list[str], top_k: int | None = None) -> list[tuple[int, float]]:
        """调用 TEI /rerank 接口，返回 [(original_index, score), ...] 按 score 降序"""
        logger.debug("Rerank 请求开始, query_len={}, texts_count={}, top_k={}", len(query), len(texts), top_k)
        resp = await self._client.post(
            f"{self.base_url}/rerank",
            json={"query": query, "texts": texts, "truncate": True},
        )
        resp.raise_for_status()
        results = resp.json()  # [{"index": 0, "score": 0.95}, ...]
        ranked = sorted(results, key=lambda x: x["score"], reverse=True)
        if top_k:
            ranked = ranked[:top_k]
        logger.debug(
            "Rerank 完成, 保留 {} 个结果, 最高分={:.4f}",
            len(ranked),
            ranked[0]["score"] if ranked else 0.0,
        )
        return [(r["index"], r["score"]) for r in ranked]

    async def close(self):
        await self._client.aclose()


REWRITE_PROMPT = (
    "你是一个查询改写助手。将用户的自然语言问题改写为更适合向量检索的查询。\n\n"
    "规则：\n"
    "- 提取关键技术术语和概念\n"
    "- 去除口语化表达，保留核心语义\n"
    "- 如果问题涉及代码，包含可能的函数名、类名、模块名\n"
    "- 只输出改写后的查询，不要解释\n"
    "- 如果原始问题已经足够精确，直接返回原文"
)


async def rewrite_query(question: str, vllm_url: str, model: str) -> str:
    """用 LLM 将模糊问题改写为更精确的检索查询。"""
    # 短查询无需改写，直接返回原文
    if len(question) < 15:
        logger.debug("查询改写跳过: 问题过短, len={}", len(question))
        return question

    logger.debug("查询改写开始, question={}", question[:100])
    messages = [
        {"role": "system", "content": REWRITE_PROMPT},
        {"role": "user", "content": f"/no_think\n{question}" if settings.llm_no_think else question},
    ]
    try:
        rewritten = await generate_sync(messages, vllm_url, model, max_tokens=100)
        rewritten = rewritten.strip() or question
        # 改写结果过短说明过度压缩，回退到原始查询
        if len(rewritten) < len(question) / 2:
            logger.info("查询改写结果过短, rewritten='{}', 回退到原始查询", rewritten)
            return question
        logger.info("查询改写完成, original='{}', rewritten='{}'", question[:80], rewritten[:80])
        return rewritten
    except Exception:
        logger.warning("查询改写失败, 使用原始问题", exc_info=True)
        return question


@dataclass
class RetrievalTrace:
    """Captures intermediate results from each pipeline stage."""

    rewritten_query: str | None = None
    vector_results: list[ScoredChunk] | None = None
    reranked_results: list[ScoredChunk] | None = None
    final_results: list[ScoredChunk] | None = None
    intent: str = ""
    timings: dict[str, float] | None = None


async def retrieve(
    question: str,
    project: str,
    top_k: int,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None = None,
    use_graph_rag: bool = True,
    graph_store: GraphStore | None = None,
    *,
    debug: bool = False,
) -> list[ScoredChunk] | tuple[list[ScoredChunk], RetrievalTrace]:
    """Retrieve relevant chunks. If debug=True, also returns a RetrievalTrace."""
    with _tracer.start_as_current_span("rag.retrieve") as span:
        span.set_attribute("rag.query", question)
        span.set_attribute("rag.project", project)
        span.set_attribute("rag.top_k", top_k)
        t0 = time.monotonic()
        timings: dict[str, float] = {}

        logger.info("RAG 查询开始, project={}, question={}, top_k={}", project, question[:100], top_k)

        # Query 改写
        search_query = question
        rewritten: str | None = None
        if settings.query_rewrite_enabled:
            t_rw = time.monotonic()
            search_query = await rewrite_query(question, settings.vllm_url, settings.llm_model)
            timings["rewrite_ms"] = round((time.monotonic() - t_rw) * 1000, 2)
            if search_query != question:
                rewritten = search_query
                logger.info(
                    "查询已改写: '{}' -> '{}', 耗时 {:.1f}ms", question[:60], search_query[:60], timings["rewrite_ms"]
                )
            else:
                logger.debug("查询改写未变更, 耗时 {:.1f}ms", timings["rewrite_ms"])

        # 向量检索
        with _tracer.start_as_current_span("rag.vector_search") as vs_span:
            initial_top_k = settings.retrieve_top_k if reranker else top_k

            # Embedding
            t_embed = time.monotonic()
            embed_result = await embedding_client.embed_all([search_query])
            query_vector = embed_result.dense[0]
            query_sparse = embed_result.sparse[0] if embed_result.sparse else None
            timings["embed_ms"] = round((time.monotonic() - t_embed) * 1000, 2)
            logger.debug(
                "Embedding 完成, dense_dim={}, sparse={}, 耗时 {:.1f}ms",
                len(query_vector),
                query_sparse is not None,
                timings["embed_ms"],
            )
            vs_span.set_attribute("rag.vector_search.embed_ms", timings["embed_ms"])

            # Qdrant search
            t_search = time.monotonic()
            results = await vector_store.search(
                collection=project, vector=query_vector, sparse_vector=query_sparse, top_k=initial_top_k
            )
            timings["search_ms"] = round((time.monotonic() - t_search) * 1000, 2)
            logger.debug(
                "向量检索完成, 返回 {} 个候选, top_k={}, 耗时 {:.1f}ms",
                len(results),
                initial_top_k,
                timings["search_ms"],
            )
            vs_span.set_attribute("rag.vector_search.search_ms", timings["search_ms"])
            vs_span.set_attribute("rag.vector_search.num_results", len(results))

        chunks: list[ScoredChunk] = []
        for point in results:
            payload = point.payload or {}
            chunks.append(
                ScoredChunk(
                    content=payload.get("text", payload.get("content", "")),
                    file_path=payload.get("file_path", ""),
                    start_line=payload.get("start_line"),
                    end_line=payload.get("end_line"),
                    score=point.score,
                    vector_score=point.score,
                    node_type=payload.get("node_type", ""),
                    language=payload.get("language", ""),
                    repo_url=payload.get("repo_url", ""),
                )
            )

        vector_results = list(chunks) if debug else None

        # Graph RAG 扩展：在 rerank 之前，通过图谱关系补充关联代码片段
        if use_graph_rag and chunks:
            from delphi.retrieval.graph_rag import expand_with_graph

            pre_len = len(chunks)
            chunks = expand_with_graph(chunks, project, graph_store=graph_store)
            for c in chunks[pre_len:]:
                c.from_graph = True
            if len(chunks) > pre_len:
                logger.info("Graph RAG 扩展后 chunk 数: {} -> {}", pre_len, len(chunks))

        # Rerank 阶段
        if reranker and chunks:
            with _tracer.start_as_current_span("rag.rerank") as rr_span:
                t_rr = time.monotonic()
                texts = [c.content for c in chunks]
                rerank_top_k = min(settings.reranker_top_k, top_k)
                ranked = await reranker.rerank(query=question, texts=texts, top_k=rerank_top_k)
                timings["rerank_ms"] = round((time.monotonic() - t_rr) * 1000, 2)
                rr_span.set_attribute("rag.rerank.input_count", len(chunks))
                rr_span.set_attribute("rag.rerank.output_count", len(ranked))
                reranked_chunks = [
                    ScoredChunk(
                        content=chunks[idx].content,
                        file_path=chunks[idx].file_path,
                        start_line=chunks[idx].start_line,
                        end_line=chunks[idx].end_line,
                        score=score,
                        vector_score=chunks[idx].vector_score,
                        from_graph=chunks[idx].from_graph,
                        node_type=chunks[idx].node_type,
                        language=chunks[idx].language,
                        repo_url=chunks[idx].repo_url,
                    )
                    for idx, score in ranked
                ]

                # Low-score fallback: if top-1 reranker score is below threshold,
                # the reranker has low confidence — fall back to original vector ordering.
                top1_score = ranked[0][1] if ranked else 0.0
                rr_span.set_attribute("rag.rerank.top1_score", top1_score)
                if top1_score < settings.reranker_score_threshold:
                    logger.info(
                        "Reranker 置信度不足, top1_score={:.4f} < threshold={:.4f}, 回退到向量排序",
                        top1_score,
                        settings.reranker_score_threshold,
                    )
                    rr_span.set_attribute("rag.rerank.fallback", True)
                    # Use original vector-score-sorted chunks sliced to top_k
                    chunks = sorted(chunks, key=lambda c: c.vector_score, reverse=True)[:top_k]
                else:
                    chunks = reranked_chunks

        reranked_results = list(chunks) if debug else None

        t_dd = time.monotonic()
        pre_dedup_len = len(chunks)
        chunks = deduplicate_chunks(chunks)
        timings["dedup_ms"] = round((time.monotonic() - t_dd) * 1000, 2)
        logger.debug("去重完成, {} -> {} 个 chunk, 耗时 {:.1f}ms", pre_dedup_len, len(chunks), timings["dedup_ms"])

        elapsed = time.monotonic() - t0
        timings["total_ms"] = round(elapsed * 1000, 2)
        span.set_attribute("rag.retrieve.latency_ms", round(elapsed * 1000, 2))
        span.set_attribute("rag.retrieve.num_results", len(chunks))

        logger.info(
            "RAG 查询完成, project={}, 返回 {} 个结果, 总耗时 {:.1f}ms",
            project,
            len(chunks),
            timings["total_ms"],
        )

        if debug:
            trace = RetrievalTrace(
                rewritten_query=rewritten,
                vector_results=vector_results,
                reranked_results=reranked_results,
                final_results=list(chunks),
                timings=timings,
            )
            return chunks, trace
        return chunks


def _line_overlap_ratio(s1: int, e1: int, s2: int, e2: int) -> float:
    """计算两个行范围的重叠比例（相对于较小的范围）。"""
    overlap_start = max(s1, s2)
    overlap_end = min(e1, e2)
    if overlap_start > overlap_end:
        return 0.0
    overlap_len = overlap_end - overlap_start + 1
    min_len = min(e1 - s1 + 1, e2 - s2 + 1)
    return overlap_len / min_len if min_len > 0 else 0.0


def deduplicate_chunks(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """去重与合并检索结果。

    1. 完全重复去重：相同 content 的 chunks 只保留 score 最高的
    2. 重叠去重：同一文件中行范围重叠超过 50% 的，只保留 score 高的
    """
    if not chunks:
        return chunks

    logger.debug("开始去重, 输入 {} 个 chunk", len(chunks))

    # 1. 完全重复去重（相同 content）
    seen_content: dict[str, int] = {}  # content -> index of best chunk
    unique: list[ScoredChunk] = []
    for chunk in chunks:
        key = chunk.content
        if key in seen_content:
            idx = seen_content[key]
            if chunk.score > unique[idx].score:
                unique[idx] = chunk
        else:
            seen_content[key] = len(unique)
            unique.append(chunk)

    # 2. 重叠去重：同一文件中行范围重叠 > 50% 的，保留 score 高的
    result: list[ScoredChunk] = []
    for chunk in sorted(unique, key=lambda c: c.score, reverse=True):
        is_overlap = False
        if chunk.start_line is not None and chunk.end_line is not None:
            for existing in result:
                if (
                    existing.file_path == chunk.file_path
                    and existing.start_line is not None
                    and existing.end_line is not None
                ):
                    overlap = _line_overlap_ratio(
                        chunk.start_line,
                        chunk.end_line,
                        existing.start_line,
                        existing.end_line,
                    )
                    if overlap > 0.5:
                        is_overlap = True
                        logger.trace(
                            "重叠去重: 丢弃 chunk file={}, lines={}-{}, overlap={:.2f}",
                            chunk.file_path,
                            chunk.start_line,
                            chunk.end_line,
                            overlap,
                        )
                        break
        if not is_overlap:
            result.append(chunk)

    logger.debug("去重结果: 内容去重 {} -> {}, 重叠去重 {} -> {}", len(chunks), len(unique), len(unique), len(result))
    return result


def build_prompt(question: str, chunks: list[ScoredChunk], history: list[dict] | None = None) -> list[dict]:
    with _tracer.start_as_current_span("rag.prompt_build") as span:
        span.set_attribute("rag.prompt_build.num_chunks", len(chunks))
        logger.debug("构建 Prompt 开始, chunks={}, history_len={}", len(chunks), len(history) if history else 0)
        context_parts: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            header = f"[{i}] [来源: {chunk.file_path}"
            if chunk.start_line is not None and chunk.end_line is not None:
                header += f", 行 {chunk.start_line}-{chunk.end_line}"
            header += "]"
            context_parts.append(f"{header}\n{chunk.content}")

        context_block = "\n\n".join(context_parts)
        no_think_prefix = "/no_think\n" if settings.llm_no_think else ""
        user_content = (
            f"{no_think_prefix}---上下文开始---\n{context_block}\n---上下文结束---\n\n用户问题：{question}\n\n请回答："
        )

        intent = classify_intent(question)
        system_prompt = get_system_prompt(intent)

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        span.set_attribute("rag.prompt_build.intent", str(intent))
        logger.debug(
            "Prompt 构建完成, intent={}, messages_count={}, context_len={}",
            intent,
            len(messages),
            len(context_block),
        )
        return messages


def _llm_headers() -> dict[str, str]:
    if settings.llm_api_key:
        return {"Authorization": f"Bearer {settings.llm_api_key}"}
    return {}


async def generate(messages: list[dict], vllm_url: str, model: str) -> AsyncIterator[str]:
    with _tracer.start_as_current_span("rag.llm_call") as span:
        span.set_attribute("rag.llm.model", model)
        span.set_attribute("rag.llm.stream", True)
        t0 = time.monotonic()
        url = f"{vllm_url.rstrip('/')}/v1/chat/completions"
        payload = {"model": model, "messages": messages, "stream": True}
        headers = _llm_headers()
        logger.info("LLM 流式调用开始, model={}, messages_count={}", model, len(messages))
        async with (
            httpx.AsyncClient(timeout=300.0) as client,
            client.stream("POST", url, json=payload, headers=headers) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: ") :]
                if data.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = obj.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        span.set_attribute("rag.llm.latency_ms", latency_ms)
        logger.info("LLM 流式调用完成, model={}, 耗时 {:.1f}ms", model, latency_ms)


async def generate_sync(messages: list[dict], vllm_url: str, model: str, max_tokens: int | None = None) -> str:
    with _tracer.start_as_current_span("rag.llm_call") as span:
        span.set_attribute("rag.llm.model", model)
        span.set_attribute("rag.llm.stream", False)
        t0 = time.monotonic()
        url = f"{vllm_url.rstrip('/')}/v1/chat/completions"
        payload: dict = {"model": model, "messages": messages, "stream": False}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        headers = _llm_headers()
        logger.info("LLM 同步调用开始, model={}, messages_count={}, max_tokens={}", model, len(messages), max_tokens)
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            span.set_attribute("rag.llm.latency_ms", latency_ms)
            content = data["choices"][0]["message"]["content"]
            logger.info("LLM 同步调用完成, model={}, 耗时 {:.1f}ms, 响应长度={}", model, latency_ms, len(content))
            return content
