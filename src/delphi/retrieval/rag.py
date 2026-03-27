from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from delphi.core.config import settings
from delphi.retrieval.intent import classify_intent, get_system_prompt

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from delphi.core.clients import EmbeddingClient, VectorStore

logger = logging.getLogger(__name__)

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


class RerankerClient:
    """TEI Reranker 服务客户端"""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.reranker_url).rstrip("/")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def rerank(
        self, query: str, texts: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """调用 TEI /rerank 接口，返回 [(original_index, score), ...] 按 score 降序"""
        resp = await self._client.post(
            f"{self.base_url}/rerank",
            json={"query": query, "texts": texts, "truncate": True},
        )
        resp.raise_for_status()
        results = resp.json()  # [{"index": 0, "score": 0.95}, ...]
        ranked = sorted(results, key=lambda x: x["score"], reverse=True)
        if top_k:
            ranked = ranked[:top_k]
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
    messages = [
        {"role": "system", "content": REWRITE_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        rewritten = await generate_sync(messages, vllm_url, model)
        return rewritten.strip() or question
    except Exception:
        logger.warning("Query rewrite failed, using original question", exc_info=True)
        return question


async def retrieve(
    question: str,
    project: str,
    top_k: int,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None = None,
) -> list[ScoredChunk]:
    # Query 改写
    search_query = question
    if settings.query_rewrite_enabled:
        search_query = await rewrite_query(question, settings.vllm_url, settings.llm_model)
        if search_query != question:
            logger.info("Query rewritten: '%s' -> '%s'", question, search_query)

    # 如果启用了 reranker，先用更大的 retrieve_top_k 召回
    initial_top_k = settings.retrieve_top_k if reranker else top_k
    embed_result = await embedding_client.embed_all([search_query])
    query_vector = embed_result.dense[0]
    query_sparse = embed_result.sparse[0]
    results = await vector_store.search(
        collection=project, vector=query_vector, sparse_vector=query_sparse, top_k=initial_top_k
    )
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
            )
        )

    # Rerank 阶段
    if reranker and chunks:
        texts = [c.content for c in chunks]
        rerank_top_k = min(settings.reranker_top_k, top_k)
        ranked = await reranker.rerank(query=question, texts=texts, top_k=rerank_top_k)
        chunks = [
            ScoredChunk(
                content=chunks[idx].content,
                file_path=chunks[idx].file_path,
                start_line=chunks[idx].start_line,
                end_line=chunks[idx].end_line,
                score=score,
            )
            for idx, score in ranked
        ]

    chunks = deduplicate_chunks(chunks)
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
                        break
        if not is_overlap:
            result.append(chunk)

    return result


def build_prompt(
    question: str, chunks: list[ScoredChunk], history: list[dict] | None = None
) -> list[dict]:
    context_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[{i}] [来源: {chunk.file_path}"
        if chunk.start_line is not None and chunk.end_line is not None:
            header += f", 行 {chunk.start_line}-{chunk.end_line}"
        header += "]"
        context_parts.append(f"{header}\n{chunk.content}")

    context_block = "\n\n".join(context_parts)
    user_content = f"---上下文开始---\n{context_block}\n---上下文结束---\n\n用户问题：{question}\n\n请回答："

    intent = classify_intent(question)
    system_prompt = get_system_prompt(intent)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages


async def generate(messages: list[dict], vllm_url: str, model: str) -> AsyncIterator[str]:
    url = f"{vllm_url.rstrip('/')}/v1/chat/completions"
    payload = {"model": model, "messages": messages, "stream": True}
    async with httpx.AsyncClient(timeout=120.0) as client, client.stream("POST", url, json=payload) as resp:
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


async def generate_sync(messages: list[dict], vllm_url: str, model: str) -> str:
    url = f"{vllm_url.rstrip('/')}/v1/chat/completions"
    payload = {"model": model, "messages": messages, "stream": False}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
