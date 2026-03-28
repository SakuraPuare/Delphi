"""评估任务 API 路由"""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from delphi.api.models import TaskInfo
from delphi.evaluation.dataset import generate_eval_dataset, resume_eval_dataset
from delphi.evaluation.runner import resume_evaluation, run_evaluation
from delphi.ingestion.pipeline import create_task

router = APIRouter(prefix="/eval", tags=["eval"])


class EvalRunRequest(BaseModel):
    dataset_path: str
    project_id: str | None = None


class DatasetGenRequest(BaseModel):
    project_id: str
    num_questions: int = 50
    output_path: str | None = None


@router.post("/run", response_model=TaskInfo, status_code=202)
async def start_eval(body: EvalRunRequest, request: Request) -> TaskInfo:
    """启动评估任务。"""
    params = {"dataset_path": body.dataset_path, "project_id": body.project_id}
    task_id = create_task(task_type="eval_run", params=params)

    async def _run():
        try:
            await run_evaluation(body.dataset_path, body.project_id, task_id=task_id)
        except Exception as e:
            from delphi.api.websocket import task_manager

            task_manager.fail_task(task_id, str(e))

    asyncio.create_task(_run())
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/generate", response_model=TaskInfo, status_code=202)
async def start_dataset_gen(body: DatasetGenRequest, request: Request) -> TaskInfo:
    """启动评估数据集生成任务。"""
    params = {"project_id": body.project_id, "num_questions": body.num_questions, "output_path": body.output_path}
    task_id = create_task(task_type="dataset_gen", params=params)

    async def _run():
        try:
            await generate_eval_dataset(body.project_id, body.num_questions, body.output_path, task_id=task_id)
        except Exception as e:
            from delphi.api.websocket import task_manager

            task_manager.fail_task(task_id, str(e))

    asyncio.create_task(_run())
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/tasks/{task_id}/resume", response_model=TaskInfo, status_code=202)
async def resume_eval_task(task_id: str, request: Request) -> TaskInfo:
    """从断点恢复评估任务。"""
    from delphi.core.task_store import TaskStore  # noqa: TC001

    store: TaskStore | None = getattr(request.app.state, "task_store", None)
    if not store:
        raise HTTPException(500, detail="TaskStore not initialized")

    task_data = store.load(task_id)
    if not task_data:
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")

    task_type = task_data.get("task_type", "")

    if task_type == "eval_run":

        async def _run():
            try:
                await resume_evaluation(task_id)
            except Exception as e:
                from delphi.api.websocket import task_manager

                task_manager.fail_task(task_id, str(e))

        asyncio.create_task(_run())
    elif task_type == "dataset_gen":

        async def _run():
            try:
                await resume_eval_dataset(task_id)
            except Exception as e:
                from delphi.api.websocket import task_manager

                task_manager.fail_task(task_id, str(e))

        asyncio.create_task(_run())
    else:
        raise HTTPException(400, detail=f"不支持恢复的任务类型: {task_type}")

    return TaskInfo(task_id=task_id, status="running")


@router.get("/tasks")
async def list_eval_tasks(request: Request):
    """列出所有评估任务。"""
    from delphi.core.task_store import TaskStore  # noqa: TC001

    store: TaskStore | None = getattr(request.app.state, "task_store", None)
    if not store:
        return []
    return [t for t in store.list_all() if t.get("task_type") in ("eval_run", "dataset_gen")]
