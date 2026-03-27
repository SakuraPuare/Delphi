import asyncio
from pathlib import Path

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

    try:
        exporter = EXPORTERS.get(body.format)
        if not exporter:
            raise ValueError(f"不支持的格式: {body.format}")

        output_path = Path(body.output_path) if body.output_path else Path(f"finetune_{task_id}.{body.format}")

        task_manager.update_progress(task_id, 10, "生成 QA 对中")

        qa_gen = generate_qa_pairs(
            project=body.project,
            num_samples=body.num_samples,
            questions_per_chunk=body.questions_per_chunk,
            vector_store=vector_store,
        )

        task_manager.update_progress(task_id, 50, f"导出为 {body.format} 格式")

        count = await exporter(qa_gen, output_path)

        task["processed"] = count
        task["progress"] = 1.0
        task["status"] = "done"
        task["result"] = {"output_path": str(output_path), "count": count}
        task_manager.complete_task(task_id, {"output_path": str(output_path), "count": count})

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task_manager.fail_task(task_id, str(e))


@router.post("/generate", response_model=TaskInfo, status_code=202)
async def finetune_generate(body: FinetuneGenRequest, request: Request) -> TaskInfo:
    task_id = create_task(task_type="finetune")
    asyncio.create_task(
        _run_finetune_task(
            task_id=task_id,
            body=body,
            vector_store=request.app.state.vector_store,
        )
    )
    return TaskInfo(task_id=task_id, status="pending")


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def finetune_task_status(task_id: str) -> TaskInfo:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")
    return TaskInfo(**{k: v for k, v in task.items() if k in TaskInfo.model_fields})
