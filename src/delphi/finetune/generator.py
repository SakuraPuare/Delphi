"""微调数据自动生成：从知识库 chunks 生成 Q&A 训练对"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from delphi.core.clients import VectorStore
from delphi.core.config import settings
from delphi.retrieval.rag import generate_sync

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

QUESTION_GEN_PROMPT = (
    "你是一个数据标注助手。根据以下代码/文档片段，生成 {n} 个高质量的问题。\n\n"
    "要求：\n"
    "- 问题应该是用户在实际使用中可能会问的\n"
    "- 问题要具体，不要太泛泛\n"
    "- 每行一个问题，不要编号\n\n"
    "片段内容：\n{chunk}"
)

ANSWER_GEN_PROMPT = (
    "你是一个代码与文档问答助手。根据以下上下文回答问题。\n\n"
    "上下文：\n{chunk}\n\n"
    "问题：{question}\n\n"
    "要求：只基于上下文回答，简洁准确。"
)


async def generate_qa_pairs(
    project: str,
    num_samples: int = 100,
    questions_per_chunk: int = 2,
    vllm_url: str | None = None,
    model: str | None = None,
    vector_store: VectorStore | None = None,
) -> AsyncIterator[dict]:
    """从项目知识库生成 Q&A 对，yield {"question": ..., "answer": ..., "source": ...}"""
    vllm_url = vllm_url or settings.vllm_url
    model = model or settings.llm_model
    vs = vector_store or VectorStore()

    try:
        points, _next_offset = await vs._client.scroll(
            collection_name=project,
            limit=num_samples,
        )
    except Exception as e:
        logger.error("Failed to scroll collection '%s': %s", project, e)
        raise

    logger.info("Sampled %d chunks from '%s'", len(points), project)

    for point in points:
        payload = point.payload or {}
        chunk_text = payload.get("text", "")
        source = payload.get("file_path", "unknown")

        if not chunk_text.strip():
            continue

        # 生成问题
        q_prompt = QUESTION_GEN_PROMPT.format(n=questions_per_chunk, chunk=chunk_text)
        messages = [{"role": "user", "content": q_prompt}]
        try:
            raw_questions = await generate_sync(messages, vllm_url, model)
        except Exception:
            logger.warning("Failed to generate questions for chunk from %s", source, exc_info=True)
            continue

        questions = [q.strip() for q in raw_questions.strip().splitlines() if q.strip()]

        # 对每个问题生成答案
        for question in questions:
            a_prompt = ANSWER_GEN_PROMPT.format(chunk=chunk_text, question=question)
            messages = [{"role": "user", "content": a_prompt}]
            try:
                answer = await generate_sync(messages, vllm_url, model)
            except Exception:
                logger.warning("Failed to generate answer for: %s", question, exc_info=True)
                continue

            yield {
                "question": question,
                "answer": answer.strip(),
                "source": source,
            }
