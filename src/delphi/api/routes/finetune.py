import asyncio
import time
from pathlib import Path

from loguru import logger
from fastapi import APIRouter, HTTPException, Request

from delphi.api.models import FinetuneGenRequest, TaskInfo
from delphi.api.websocket import task_manager
from delphi.finetune.exporter import export_alpaca, export_jsonl, export_sharegpt
from delphi.finetune.generator import generate_qa_pairs
from delphi.ingestion.pipeline import create_task, get_task

router = APIRouter(prefix="/finetune", tags=["finetune"])

EXPORTERS = {
    "jsonl": export_jsonl,
    "alpaca": export_alpaca,
    "sharegpt": export_sharegpt,
}


async def _run_finetune_task(
    task_id: str,
    body: FinetuneGenRequest,
    vector_store,
) -> None:
    from delphi.ingestion.pipeline import _tasks

    task = _tasks[task_id]
    task["status"] = "running"
    task["total"] = body.num_samples
    task_manager.update_progress(task_id, 0, "开始生成微调数据")
    logger.info("微调数据生成任务开始, task_id={}, project={}, num_samples={}, format={}", task_id, body.project, body.num_samples, body.format)
    t_start = time.monotonic()

    try:
        exporter = EXPORTERS.get(body.format)
        if not exporter:
            logger.error("不支持的导出格式: {}", body.format)
            raise ValueError(f"不支持的格式: {body.format}")

        output_path = Path(body.output_path) if body.output_path else Path(f"finetune_{task_id}.{body.format}")
        logger.debug("微调数据输出路径: {}", output_path)

        task_manager.update_progress(task_id, 10, "生成 QA 对中")

        qa_gen = generate_qa_pairs(
            project=body.project,
            num_samples=body.num_samples,
            questions_per_chunk=body.questions_per_chunk,
            vector_store=vector_store,
        )
        logger.debug("QA 对生成器已创建, questions_per_chunk={}", body.questions_per_chunk)

        task_manager.update_progress(task_id, 50, f"导出为 {body.format} 格式")

        count = await exporter(qa_gen, output_path)

        task["processed"] = count
        task["progress"] = 1.0
        task["status"] = "done"
        task["result"] = {"output_path": str(output_path), "count": count}
        task_manager.complete_task(task_id, {"output_path": str(output_path), "count": count})

        elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
        logger.info("微调数据生成完成, task_id={}, 生成数量={}, 耗时={}ms, 输出={}", task_id, count, elapsed_ms, output_path)

    except Exception as e:
        logger.error("微调数据生成失败, task_id={}, error={}", task_id, e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
        task_manager.fail_task(task_id, str(e))


@router.post("/generate", response_model=TaskInfo, status_code=202)
async def finetune_generate(body: FinetuneGenRequest, request: Request) -> TaskInfo:
    logger.info("收到微调数据生成请求, project={}, num_samples={}, format={}", body.project, body.num_samples, body.format)
    task_id = create_task(task_type="finetune")
    asyncio.create_task(
        _run_finetune_task(
            task_id=task_id,
            body=body,
            vector_store=request.app.state.vector_store,
        )
    )
    logger.debug("微调任务已创建, task_id={}", task_id)
    return TaskInfo(task_id=task_id, status="pending")


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def finetune_task_status(task_id: str) -> TaskInfo:
    logger.debug("收到微调任务状态查询, task_id={}", task_id)
    task = get_task(task_id)
    if task is None:
        logger.warning("微调任务不存在, task_id={}", task_id)
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")
    logger.debug("返回微调任务状态, task_id={}, status={}", task_id, task.get("status"))
    return TaskInfo(**{k: v for k, v in task.items() if k in TaskInfo.model_fields})
