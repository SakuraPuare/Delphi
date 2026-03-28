import asyncio

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from delphi.api.models import DocImportRequest, GitImportRequest, MediaImportRequest, TaskInfo
from delphi.ingestion.doc_pipeline import resume_doc_import, run_doc_import
from delphi.ingestion.media_pipeline import resume_media_import, run_media_import
from delphi.ingestion.pipeline import create_task, get_task, resume_git_import, run_git_import

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
    logger.info("收到 Git 导入请求, url={}, project={}, branch={}", body.url, body.project, body.branch)
    params = {
        "url": body.url, "project": body.project, "branch": body.branch,
        "depth": body.depth, "include": body.include, "exclude": body.exclude,
    }
    task_id = create_task(task_type="git_import", params=params)
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
    logger.debug("Git 导入任务已创建, task_id={}", task_id)
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/docs", response_model=TaskInfo, status_code=202)
async def import_docs(body: DocImportRequest, request: Request) -> TaskInfo:
    logger.info("收到文档导入请求, path={}, project={}, recursive={}", body.path, body.project, body.recursive)
    params = {"path": body.path, "project": body.project, "recursive": body.recursive, "file_types": body.file_types}
    task_id = create_task(task_type="doc_import", params=params)
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
    logger.debug("文档导入任务已创建, task_id={}", task_id)
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/media", response_model=TaskInfo, status_code=202)
async def import_media(body: MediaImportRequest, request: Request) -> TaskInfo:
    logger.info("收到媒体导入请求, path={}, project={}, whisper_model={}", body.path, body.project, body.whisper_model)
    params = {
        "path": body.path, "project": body.project,
        "recursive": body.recursive, "whisper_model": body.whisper_model,
    }
    task_id = create_task(task_type="media_import", params=params)
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
    logger.debug("媒体导入任务已创建, task_id={}", task_id)
    return TaskInfo(task_id=task_id, status="pending")


@router.post("/batch", response_model=BatchImportResponse, status_code=202)
async def import_batch(body: BatchImportRequest, request: Request) -> BatchImportResponse:
    """批量导入多个 Git 仓库，并发执行。"""
    logger.info("收到批量导入请求, 仓库数={}", len(body.repos))
    tasks: list[TaskInfo] = []
    for repo in body.repos:
        params = {
            "url": repo.url, "project": repo.project_name, "branch": repo.branch,
            "depth": body.depth, "include": body.include, "exclude": body.exclude,
        }
        task_id = create_task(task_type="git_import", params=params)
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
        logger.debug("批量导入子任务已创建, task_id={}, url={}", task_id, repo.url)
        tasks.append(TaskInfo(task_id=task_id, status="pending"))
    logger.info("批量导入任务全部创建完成, 任务数={}", len(tasks))
    return BatchImportResponse(tasks=tasks)


@router.get("/tasks", response_model=list[TaskInfo])
async def list_tasks(request: Request) -> list[TaskInfo]:
    """列出所有导入任务（含历史）。"""
    logger.debug("收到列出导入任务请求")
    from delphi.core.task_store import TaskStore  # noqa: TC001
    store: TaskStore | None = getattr(request.app.state, "task_store", None)
    if store:
        result = [TaskInfo(**{k: v for k, v in t.items() if k in TaskInfo.model_fields}) for t in store.list_all()]
        logger.debug("返回导入任务列表, 任务数={}", len(result))
        return result
    logger.debug("TaskStore 未初始化, 返回空列表")
    return []


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task_status(task_id: str) -> TaskInfo:
    logger.debug("收到查询任务状态请求, task_id={}", task_id)
    task = get_task(task_id)
    if task is None:
        logger.warning("任务不存在, task_id={}", task_id)
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")
    logger.debug("返回任务状态, task_id={}, status={}", task_id, task.get("status"))
    return TaskInfo(**task)


@router.post("/tasks/{task_id}/resume", response_model=TaskInfo, status_code=202)
async def resume_task(task_id: str, request: Request) -> TaskInfo:
    """从断点恢复导入任务。"""
    logger.info("收到恢复任务请求, task_id={}", task_id)
    from delphi.core.task_store import TaskStore  # noqa: TC001
    store: TaskStore | None = getattr(request.app.state, "task_store", None)
    if not store:
        logger.error("恢复任务失败: TaskStore 未初始化")
        raise HTTPException(500, detail="TaskStore not initialized")

    task_data = store.load(task_id)
    if not task_data:
        logger.warning("恢复任务失败: 任务不存在, task_id={}", task_id)
        raise HTTPException(404, detail=f"任务 '{task_id}' 不存在")

    task_type = task_data.get("task_type", "")
    logger.debug("恢复任务类型: task_id={}, task_type={}", task_id, task_type)

    if task_type == "git_import":
        asyncio.create_task(resume_git_import(
            task_id, embedding=request.app.state.embedding, vector_store=request.app.state.vector_store
        ))
    elif task_type == "doc_import":
        asyncio.create_task(resume_doc_import(
            task_id, embedding=request.app.state.embedding, vector_store=request.app.state.vector_store
        ))
    elif task_type == "media_import":
        asyncio.create_task(resume_media_import(
            task_id, embedding=request.app.state.embedding, vector_store=request.app.state.vector_store
        ))
    else:
        logger.error("不支持恢复的任务类型: task_type={}", task_type)
        raise HTTPException(400, detail=f"不支持恢复的任务类型: {task_type}")

    logger.info("任务恢复已启动, task_id={}, task_type={}", task_id, task_type)
    return TaskInfo(task_id=task_id, status="running")
