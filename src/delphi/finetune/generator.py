"""微调数据自动生成：从知识库 chunks 生成 Q&A 训练对"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from delphi.core.clients import VectorStore
from delphi.core.config import settings
from delphi.retrieval.rag import generate_sync

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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
    logger.info("微调 QA 生成器初始化: project={}, model={}, num_samples={}, questions_per_chunk={}", project, model, num_samples, questions_per_chunk)

    try:
        points, _next_offset = await vs._client.scroll(
            collection_name=project,
            limit=num_samples,
        )
    except Exception as e:
        logger.error("知识库滚动查询失败: project={}, error={}", project, e)
        raise

    logger.info("微调数据生成开始: project={}, 采样 {} 个 chunks, 每 chunk 生成 {} 个问题", project, len(points), questions_per_chunk)

    for point in points:
        payload = point.payload or {}
        chunk_text = payload.get("text", "")
        source = payload.get("file_path", "unknown")

        if not chunk_text.strip():
            logger.debug("chunk 文本为空, 跳过: source={}", source)
            continue

        # 生成问题
        q_prompt = QUESTION_GEN_PROMPT.format(n=questions_per_chunk, chunk=chunk_text)
        messages = [{"role": "user", "content": q_prompt}]
        try:
            raw_questions = await generate_sync(messages, vllm_url, model)
        except Exception:
            logger.warning("问题生成失败: source={}", source, exc_info=True)
            continue

        questions = [q.strip() for q in raw_questions.strip().splitlines() if q.strip()]
        logger.debug("生成 {} 个问题, source={}", len(questions), source)

        # 对每个问题生成答案
        for question in questions:
            a_prompt = ANSWER_GEN_PROMPT.format(chunk=chunk_text, question=question)
            messages = [{"role": "user", "content": a_prompt}]
            try:
                answer = await generate_sync(messages, vllm_url, model)
            except Exception:
                logger.warning("答案生成失败: question={}", question[:60], exc_info=True)
                continue

            logger.debug("QA 对生成成功: question={}, source={}", question[:60], source)
            yield {
                "question": question,
                "answer": answer.strip(),
                "source": source,
            }
