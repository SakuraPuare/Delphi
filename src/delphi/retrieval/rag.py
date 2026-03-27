from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from delphi.core.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from delphi.core.clients import EmbeddingClient, VectorStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一个代码与文档问答助手。请根据以下检索到的上下文内容回答用户的问题。\n\n"
    "规则：\n"
    "- 只基于提供的上下文回答，不要编造信息\n"
    '- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"\n'
    "- 回答时引用具体的文件或章节名称\n"
    "- 代码示例使用代码块格式"
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


async def retrieve(
    question: str,
    project: str,
    top_k: int,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None = None,
) -> list[ScoredChunk]:
    # 如果启用了 reranker，先用更大的 retrieve_top_k 召回
    initial_top_k = settings.retrieve_top_k if reranker else top_k
    embed_result = await embedding_client.embed_all([question])
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

    return chunks


def build_prompt(question: str, chunks: list[ScoredChunk]) -> list[dict]:
    context_parts: list[str] = []
    for chunk in chunks:
        header = f"[来源: {chunk.file_path}"
        if chunk.start_line is not None and chunk.end_line is not None:
            header += f", 行 {chunk.start_line}-{chunk.end_line}"
        header += "]"
        context_parts.append(f"{header}\n{chunk.content}")

    context_block = "\n\n".join(context_parts)
    user_content = f"---上下文开始---\n{context_block}\n---上下文结束---\n\n用户问题：{question}\n\n请回答："
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


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
