from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

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


async def retrieve(
    question: str,
    project: str,
    top_k: int,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> list[ScoredChunk]:
    vectors = await embedding_client.embed([question])
    query_vector = vectors[0]
    results = await vector_store.search(collection=project, vector=query_vector, top_k=top_k)
    chunks: list[ScoredChunk] = []
    for point in results:
        payload = point.payload or {}
        chunks.append(
            ScoredChunk(
                content=payload.get("content", ""),
                file_path=payload.get("file_path", ""),
                start_line=payload.get("start_line"),
                end_line=payload.get("end_line"),
                score=point.score,
            )
        )
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
