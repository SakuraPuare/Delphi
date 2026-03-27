import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from delphi.api.models import DocImportRequest, GitImportRequest, MediaImportRequest, TaskInfo
from delphi.ingestion.doc_pipeline import run_doc_import
from delphi.ingestion.media_pipeline import run_media_import
from delphi.ingestion.pipeline import create_task, get_task, run_git_import

router = APIRouter(prefix="/import", tags=["import"])


# ------------------------------------------------------------------
# Batch import models
# ------------------------------------------------------------------


class BatchRepoItem(BaseModel):
    url: str
    branch: str = "main"
    project_name: str


class BatchImportRequest(BaseModel):
    repos: list[BatchRepoItem]
    depth: int = 1
    include: list[str] = []
    exclude: list[str] = []


class BatchImportResponse(BaseModel):
    tasks: list[TaskInfo]


@router.post("/git", response_model=TaskInfo, status_code=202)
async def import_git(body: GitImportRequest, request: Request) -> TaskInfo:
    task_id = create_task(task_type="git_import")
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
async def import_docs(body: DocImportRequest, request: Request) -> TaskInfo:
    task_id = create_task(task_type="doc_import")
    asyncio.create_task(
        run_doc_import(
            task_id=task_id,
            path=body.path,
            project=body.project,
            recursive=body.recursive,
            file_types=body.file_types,
            embedding=request.app.state.embedding,
            vector_store=request.app.state.vector_store,
        )
    )
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/media", response_model=TaskInfo, status_code=202)
async def import_media(body: MediaImportRequest, request: Request) -> TaskInfo:
    task_id = create_task(task_type="media_import")
    asyncio.create_task(
        run_media_import(
            task_id=task_id,
            path=body.path,
            project=body.project,
            recursive=body.recursive,
            whisper_model=body.whisper_model,
            embedding=request.app.state.embedding,
            vector_store=request.app.state.vector_store,
        )
    )
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/batch", response_model=BatchImportResponse, status_code=202)
async def import_batch(body: BatchImportRequest, request: Request) -> BatchImportResponse:
    """批量导入多个 Git 仓库，并发执行。"""
    tasks: list[TaskInfo] = []
    for repo in body.repos:
        task_id = create_task(task_type="git_import")
        asyncio.create_task(
            run_git_import(
                task_id=task_id,
                url=repo.url,
                project=repo.project_name,
                branch=repo.branch,
                depth=body.depth,
                include=body.include or None,
                exclude=body.exclude or None,
                embedding=request.app.state.embedding,
                vector_store=request.app.state.vector_store,
            )
        )
        tasks.append(TaskInfo(task_id=task_id, status="pending"))
    return BatchImportResponse(tasks=tasks)


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task_status(task_id: str) -> TaskInfo:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")
    return TaskInfo(**task)
