from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from delphi.core.clients import EmbeddingClient, VectorStore
from delphi.core.config import settings
from delphi.evaluation.metrics import (
    generation_faithfulness,
    generation_relevance,
    retrieval_mrr,
    retrieval_precision,
    retrieval_recall,
)
from delphi.retrieval.rag import RerankerClient, build_prompt, generate_sync, retrieve

logger = logging.getLogger(__name__)


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


async def run_evaluation(dataset_path: str, project_id: str | None = None) -> dict[str, Any]:
    """运行完整评估流水线。

    Args:
        dataset_path: 评估数据集 JSON 文件路径。
        project_id: 项目 ID，若为 None 则使用数据集中的 project_id。

    Returns:
        包含逐条结果和汇总指标的字典。
    """
    dataset = EvalDataset.from_json(dataset_path)
    pid = project_id or dataset.project_id

    embedding_client = EmbeddingClient()
    vector_store = VectorStore()
    reranker = RerankerClient() if settings.reranker_enabled else None

    results: list[EvalResult] = []
    t0 = time.monotonic()

    try:
        for i, item in enumerate(dataset.items):
            logger.info("Evaluating [%d/%d]: %s", i + 1, len(dataset.items), item.question[:60])
            result = await _eval_single(item, pid, embedding_client, vector_store, reranker)
            results.append(result)
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
    return summary
