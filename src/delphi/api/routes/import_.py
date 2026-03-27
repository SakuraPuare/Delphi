import asyncio

from fastapi import APIRouter, HTTPException, Request

from delphi.api.models import DocImportRequest, GitImportRequest, TaskInfo
from delphi.ingestion.pipeline import create_task, get_task, run_git_import

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/git", response_model=TaskInfo, status_code=202)
async def import_git(body: GitImportRequest, request: Request) -> TaskInfo:
    task_id = create_task()
    asyncio.create_task(
        run_git_import(
            task_id=task_id,
            url=body.url,
            project=body.project,
            branch=body.branch,
            depth=body.depth,
            include=body.include or None,
            exclude=body.exclude or None,
            embedding=request.app.state.embedding,
            vector_store=request.app.state.vector_store,
        )
    )
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/docs", response_model=TaskInfo, status_code=202)
async def import_docs(body: DocImportRequest) -> TaskInfo:
    # TODO: 实现文档导入
    raise HTTPException(501, detail="文档导入尚未实现")


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task_status(task_id: str) -> TaskInfo:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")
    return TaskInfo(**task)
