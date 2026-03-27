from __future__ import annotations

import logging

from delphi.core.config import settings
from delphi.retrieval.rag import generate_sync

logger = logging.getLogger(__name__)


def retrieval_recall(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """检索召回率：relevant 中被检索到的比例。"""
    if not relevant_ids:
        return 0.0
    relevant_set = set(relevant_ids)
    hits = sum(1 for rid in retrieved_ids if rid in relevant_set)
    return hits / len(relevant_set)


def retrieval_precision(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """检索精确率：检索结果中 relevant 的比例。"""
    if not retrieved_ids:
        return 0.0
    relevant_set = set(relevant_ids)
    hits = sum(1 for rid in retrieved_ids if rid in relevant_set)
    return hits / len(retrieved_ids)


def retrieval_mrr(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
    """Mean Reciprocal Rank：第一个 relevant 结果的倒数排名。"""
    if not relevant_ids:
        return 0.0
    relevant_set = set(relevant_ids)
    for rank, rid in enumerate(retrieved_ids, 1):
        if rid in relevant_set:
            return 1.0 / rank
    return 0.0


FAITHFULNESS_PROMPT = (
    "你是一个评估助手。判断以下回答是否忠实于给定的上下文内容。\n\n"
    "规则：\n"
    "- 如果回答中的所有关键信息都能在上下文中找到依据，输出 'faithful'\n"
    "- 如果回答包含上下文中没有的信息或与上下文矛盾，输出 'unfaithful'\n"
    "- 只输出一个词：faithful 或 unfaithful"
)

RELEVANCE_PROMPT = (
    "你是一个评估助手。判断以下回答是否与用户的问题相关。\n\n"
    "规则：\n"
    "- 如果回答直接回应了用户的问题，输出 'relevant'\n"
    "- 如果回答偏离主题或未回答问题，输出 'irrelevant'\n"
    "- 只输出一个词：relevant 或 irrelevant"
)


async def generation_faithfulness(answer: str, contexts: list[str]) -> float:
    """基于 LLM 判断生成内容是否忠于上下文。

    返回 1.0（faithful）或 0.0（unfaithful）。
    """
    context_block = "\n\n".join(f"[上下文 {i}]\n{ctx}" for i, ctx in enumerate(contexts, 1))
    messages = [
        {"role": "system", "content": FAITHFULNESS_PROMPT},
        {"role": "user", "content": f"/no_think\n上下文：\n{context_block}\n\n回答：\n{answer}"},
    ]
    try:
        result = await generate_sync(messages, settings.vllm_url, settings.llm_model, max_tokens=10)
        return 1.0 if "faithful" in result.strip().lower() else 0.0
    except Exception:
        logger.warning("Faithfulness evaluation failed", exc_info=True)
        return 0.0


async def generation_relevance(answer: str, question: str) -> float:
    """基于 LLM 判断回答是否与问题相关。

    返回 1.0（relevant）或 0.0（irrelevant）。
    """
    messages = [
        {"role": "system", "content": RELEVANCE_PROMPT},
        {"role": "user", "content": f"/no_think\n问题：\n{question}\n\n回答：\n{answer}"},
    ]
    try:
        result = await generate_sync(messages, settings.vllm_url, settings.llm_model, max_tokens=10)
        return 1.0 if "relevant" in result.strip().lower() else 0.0
    except Exception:
        logger.warning("Relevance evaluation failed", exc_info=True)
        return 0.0
