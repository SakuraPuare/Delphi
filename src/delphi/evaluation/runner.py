from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from delphi.core.clients import EmbeddingClient, VectorStore
from delphi.core.config import settings
from delphi.core.task_store import TaskStore  # noqa: TC001
from delphi.evaluation.metrics import (
    generation_faithfulness,
    generation_relevance,
    retrieval_mrr,
    retrieval_precision,
    retrieval_recall,
)
from delphi.retrieval.rag import RerankerClient, build_prompt, generate_sync, retrieve

_task_store: TaskStore | None = None


def set_task_store(store: TaskStore) -> None:
    global _task_store
    _task_store = store


@dataclass
class EvalItem:
    """单条评估数据。"""

    question: str
    ground_truth_answer: str
    relevant_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class EvalDataset:
    """评估数据集。"""

    project_id: str
    items: list[EvalItem]

    @classmethod
    def from_json(cls, path: str | Path) -> EvalDataset:
        """从 JSON 文件加载评估数据集。"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = [
            EvalItem(
                question=item["question"],
                ground_truth_answer=item["ground_truth_answer"],
                relevant_chunk_ids=item.get("relevant_chunk_ids", []),
            )
            for item in data["items"]
        ]
        return cls(project_id=data["project_id"], items=items)


@dataclass
class EvalResult:
    """单条评估结果。"""

    question: str
    answer: str
    retrieved_ids: list[str]
    recall: float
    precision: float
    mrr: float
    faithfulness: float
    relevance: float


async def _eval_single(
    item: EvalItem,
    project_id: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None,
) -> EvalResult:
    """对单条数据执行 retrieve + generate + 评估。"""
    logger.debug("开始单条评估: question={}", item.question[:80])
    # Retrieve
    chunks = await retrieve(
        question=item.question,
        project=project_id,
        top_k=settings.chunk_top_k,
        embedding_client=embedding_client,
        vector_store=vector_store,
        reranker=reranker,
    )

    # 用 file_path:start_line-end_line 作为 chunk 标识
    retrieved_ids = [f"{c.file_path}:{c.start_line}-{c.end_line}" for c in chunks if c.file_path]
    logger.debug("检索完成: 返回 {} 个 chunk, ids={}", len(retrieved_ids), retrieved_ids[:5])

    # Generate
    messages = build_prompt(item.question, chunks)
    answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)

    # 检索指标
    recall = retrieval_recall(retrieved_ids, item.relevant_chunk_ids)
    precision = retrieval_precision(retrieved_ids, item.relevant_chunk_ids)
    mrr = retrieval_mrr(retrieved_ids, item.relevant_chunk_ids)

    # 生成指标
    contexts = [c.content for c in chunks]
    faithfulness = await generation_faithfulness(answer, contexts)
    relevance = await generation_relevance(answer, item.question)

    logger.debug(
        "单条评估完成: recall={:.4f}, precision={:.4f}, mrr={:.4f}, faithfulness={:.1f}, relevance={:.1f}",
        recall,
        precision,
        mrr,
        faithfulness,
        relevance,
    )

    return EvalResult(
        question=item.question,
        answer=answer,
        retrieved_ids=retrieved_ids,
        recall=recall,
        precision=precision,
        mrr=mrr,
        faithfulness=faithfulness,
        relevance=relevance,
    )


async def run_evaluation(
    dataset_path: str,
    project_id: str | None = None,
    task_id: str | None = None,
    skip_indices: set[int] | None = None,
) -> dict[str, Any]:
    """运行完整评估流水线。

    Args:
        dataset_path: 评估数据集 JSON 文件路径。
        project_id: 项目 ID，若为 None 则使用数据集中的 project_id。
        task_id: 任务 ID，用于断点续传。
        skip_indices: 已完成的数据索引集合，恢复时跳过。

    Returns:
        包含逐条结果和汇总指标的字典。
    """
    dataset = EvalDataset.from_json(dataset_path)
    pid = project_id or dataset.project_id
    logger.info("评估开始, 数据集={}, 项目={}, 样本数={}", dataset_path, pid, len(dataset.items))

    embedding_client = EmbeddingClient()
    vector_store = VectorStore()
    reranker = RerankerClient() if settings.reranker_enabled else None

    results: list[EvalResult] = []
    completed_indices: list[int] = list(skip_indices) if skip_indices else []

    # 恢复时加载已有的部分结果
    if _task_store and task_id and skip_indices:
        task_data = _task_store.load(task_id)
        if task_data and task_data.get("checkpoint", {}).get("partial_results"):
            for r_dict in task_data["checkpoint"]["partial_results"]:
                results.append(EvalResult(**r_dict))

    t0 = time.monotonic()

    try:
        for i, item in enumerate(dataset.items):
            if skip_indices and i in skip_indices:
                continue
            logger.info("评估进度 [{}/{}]: {}", i + 1, len(dataset.items), item.question[:60])
            result = await _eval_single(item, pid, embedding_client, vector_store, reranker)
            results.append(result)
            completed_indices.append(i)
            if _task_store and task_id:
                _task_store.update_checkpoint(
                    task_id,
                    {
                        "completed_indices": completed_indices,
                        "partial_results": [asdict(r) for r in results],
                    },
                )
    finally:
        await embedding_client.close()
        await vector_store.close()
        if reranker:
            await reranker.close()

    elapsed = time.monotonic() - t0
    n = len(results)

    summary: dict[str, Any] = {
        "project_id": pid,
        "total": n,
        "elapsed_seconds": round(elapsed, 2),
        "metrics": {
            "avg_recall": round(sum(r.recall for r in results) / n, 4) if n else 0,
            "avg_precision": round(sum(r.precision for r in results) / n, 4) if n else 0,
            "avg_mrr": round(sum(r.mrr for r in results) / n, 4) if n else 0,
            "avg_faithfulness": round(sum(r.faithfulness for r in results) / n, 4) if n else 0,
            "avg_relevance": round(sum(r.relevance for r in results) / n, 4) if n else 0,
        },
        "details": [asdict(r) for r in results],
    }

    logger.info(
        "评估完成: project={}, 样本数={}, 耗时={:.2f}s, "
        "avg_recall={}, avg_precision={}, avg_mrr={}, avg_faithfulness={}, avg_relevance={}",
        pid,
        n,
        elapsed,
        summary["metrics"]["avg_recall"],
        summary["metrics"]["avg_precision"],
        summary["metrics"]["avg_mrr"],
        summary["metrics"]["avg_faithfulness"],
        summary["metrics"]["avg_relevance"],
    )

    if _task_store and task_id:
        _task_store.save(
            task_id,
            {
                "task_id": task_id,
                "task_type": "eval_run",
                "status": "done",
                "checkpoint": None,
                "result": summary,
                "updated_at": time.time(),
            },
        )

    return summary


async def resume_evaluation(task_id: str) -> dict[str, Any]:
    """从断点恢复评估任务。"""
    if not _task_store:
        raise RuntimeError("TaskStore not initialized")
    task_data = _task_store.load(task_id)
    if not task_data:
        raise ValueError(f"Task {task_id} not found")

    logger.info("恢复评估任务: task_id={}", task_id)

    params = task_data.get("params", {})
    checkpoint = task_data.get("checkpoint", {})
    skip_indices = set(checkpoint.get("completed_indices", []))

    return await run_evaluation(
        dataset_path=params["dataset_path"],
        project_id=params.get("project_id"),
        task_id=task_id,
        skip_indices=skip_indices,
    )
