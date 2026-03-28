from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from loguru import logger

from delphi.core.clients import EmbeddingClient, VectorStore
from delphi.core.config import settings
from delphi.core.task_store import TaskStore  # noqa: TC001
from delphi.retrieval.rag import generate_sync

_task_store: TaskStore | None = None


def set_task_store(store: TaskStore) -> None:
    global _task_store
    _task_store = store


GENERATE_QA_PROMPT = (
    "你是一个评估数据集生成助手。根据以下文档片段，生成一个高质量的问答对。\n\n"
    "规则：\n"
    "- 问题应该是一个自然的、用户可能会问的问题\n"
    "- 答案必须完全基于给定的文档片段\n"
    "- 问题应该有足够的复杂度，不能是简单的是/否问题\n"
    '- 用 JSON 格式输出：{"question": "...", "answer": "..."}\n'
    "- 只输出 JSON，不要其他内容"
)


async def _fetch_random_chunks(
    project_id: str,
    vector_store: VectorStore,
    embedding_client: EmbeddingClient,
    num_samples: int,
) -> list[dict[str, Any]]:
    """从向量库中随机采样 chunks。

    通过随机查询向量来近似随机采样。
    """
    # 生成随机查询向量来采样不同区域的 chunks
    sample_queries = [
        "代码实现",
        "函数定义",
        "配置说明",
        "接口文档",
        "错误处理",
        "数据结构",
        "算法逻辑",
        "模块设计",
        "API 用法",
        "测试用例",
        "部署配置",
        "性能优化",
    ]
    all_chunks: dict[str, dict[str, Any]] = {}
    logger.info("开始随机采样 chunks: project={}, 目标数量={}", project_id, num_samples)

    for query in random.sample(sample_queries, min(len(sample_queries), num_samples)):
        embed_result = await embedding_client.embed_all([query])
        query_vector = embed_result.dense[0]
        query_sparse = embed_result.sparse[0] if embed_result.sparse else None
        points = await vector_store.search(
            collection=project_id, vector=query_vector, sparse_vector=query_sparse, top_k=10
        )
        for point in points:
            payload = point.payload or {}
            chunk_id = f"{payload.get('file_path', '')}:{payload.get('start_line', '')}-{payload.get('end_line', '')}"
            if chunk_id not in all_chunks:
                all_chunks[chunk_id] = {
                    "chunk_id": chunk_id,
                    "text": payload.get("text", payload.get("content", "")),
                    "file_path": payload.get("file_path", ""),
                    "start_line": payload.get("start_line"),
                    "end_line": payload.get("end_line"),
                }

    # 随机采样指定数量
    chunks = list(all_chunks.values())
    if len(chunks) > num_samples:
        chunks = random.sample(chunks, num_samples)
    logger.info("随机采样完成: project={}, 采样到 {} 个 chunks", project_id, len(chunks))
    return chunks


async def _generate_qa_from_chunk(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """基于单个 chunk 用 LLM 生成问答对。"""
    text = chunk["text"]
    if not text or len(text.strip()) < 50:
        logger.debug("chunk 文本过短, 跳过 QA 生成: chunk_id={}", chunk["chunk_id"])
        return None

    messages = [
        {"role": "system", "content": GENERATE_QA_PROMPT},
        {"role": "user", "content": ("/no_think\n" if settings.llm_no_think else "") + f"文档片段（来源: {chunk['file_path']}）：\n{text}"},
    ]
    try:
        result = await generate_sync(messages, settings.vllm_url, settings.llm_model, max_tokens=500)
        # 提取 JSON
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        qa = json.loads(result)
        return {
            "question": qa["question"],
            "ground_truth_answer": qa["answer"],
            "relevant_chunk_ids": [chunk["chunk_id"]],
        }
    except (json.JSONDecodeError, KeyError):
        logger.warning("QA 解析失败, LLM 返回格式异常: chunk_id={}", chunk["chunk_id"])
        return None
    except Exception:
        logger.warning("QA 生成失败: chunk_id={}", chunk["chunk_id"], exc_info=True)
        return None


async def generate_eval_dataset(
    project_id: str,
    num_questions: int = 50,
    output_path: str | None = None,
    task_id: str | None = None,
    existing_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """从已有知识库自动生成评估数据集。

    Args:
        project_id: 项目 ID。
        num_questions: 要生成的问答对数量。
        output_path: 输出 JSON 文件路径，为 None 时不写文件。
        task_id: 任务 ID，用于断点续传。
        existing_items: 已有的部分结果（恢复时传入）。

    Returns:
        生成的数据集字典。
    """
    embedding_client = EmbeddingClient()
    vector_store = VectorStore()

    try:
        items: list[dict[str, Any]] = list(existing_items) if existing_items else []
        remaining = num_questions - len(items)
        logger.info(
            "评估数据集生成开始: project={}, 目标={}, 已有={}, 剩余={}",
            project_id, num_questions, len(items), remaining,
        )

        if remaining > 0:
            # 多采样一些 chunks，因为部分可能生成失败
            oversample = int(remaining * 1.5)
            chunks = await _fetch_random_chunks(project_id, vector_store, embedding_client, oversample)
            logger.info("采样 {} 个 chunks 用于 QA 生成, 过采样系数=1.5", len(chunks))

            for _i, chunk in enumerate(chunks):
                if len(items) >= num_questions:
                    break
                logger.info(
                    "QA 生成进度 [{}/{}], chunk={}",
                    len(items) + 1, num_questions, chunk.get("chunk_id", "?"),
                )
                qa = await _generate_qa_from_chunk(chunk)
                if qa:
                    items.append(qa)
                    if _task_store and task_id:
                        _task_store.update_checkpoint(task_id, {
                            "partial_items": items,
                        })

        dataset = {
            "project_id": project_id,
            "items": items,
        }

        if output_path:
            Path(output_path).write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("评估数据集已保存: path={}, 样本数={}", output_path, len(items))

        if _task_store and task_id:
            _task_store.save(task_id, {
                "task_id": task_id,
                "task_type": "dataset_gen",
                "status": "done",
                "checkpoint": None,
                "result": dataset,
                "updated_at": time.time(),
            })

        return dataset
    finally:
        await embedding_client.close()
        await vector_store.close()


async def resume_eval_dataset(task_id: str) -> dict[str, Any]:
    """从断点恢复数据集生成任务。"""
    if not _task_store:
        raise RuntimeError("TaskStore not initialized")
    task_data = _task_store.load(task_id)
    if not task_data:
        raise ValueError(f"Task {task_id} not found")

    logger.info("恢复数据集生成任务: task_id={}", task_id)

    params = task_data.get("params", {})
    checkpoint = task_data.get("checkpoint", {})
    existing_items = checkpoint.get("partial_items", [])

    return await generate_eval_dataset(
        project_id=params["project_id"],
        num_questions=params.get("num_questions", 50),
        output_path=params.get("output_path"),
        task_id=task_id,
        existing_items=existing_items,
    )
