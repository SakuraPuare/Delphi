"""调度任务管理 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------


class SchedulerJobCreate(BaseModel):
    project_id: str
    repo_url: str
    cron_expr: str = "0 */6 * * *"
    branch: str = "main"


class SchedulerJobInfo(BaseModel):
    project_id: str
    repo_url: str
    cron_expr: str
    branch: str
    next_run_at: str | None = None
    last_run_at: str | None = None
    running: bool = False


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


def _get_scheduler(request: Request):
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        logger.error("调度器未启动")
        raise HTTPException(503, detail="调度器未启动")
    return scheduler


@router.post("/jobs", response_model=SchedulerJobInfo, status_code=201)
async def create_job(body: SchedulerJobCreate, request: Request) -> SchedulerJobInfo:
    """创建定时同步任务。"""
    logger.info(
        "收到创建调度任务请求, project_id={}, repo_url={}, cron_expr={}", body.project_id, body.repo_url, body.cron_expr
    )
    scheduler = _get_scheduler(request)
    try:
        job = scheduler.add_job(
            project_id=body.project_id,
            repo_url=body.repo_url,
            cron_expr=body.cron_expr,
            branch=body.branch,
        )
    except ValueError as e:
        logger.error("创建调度任务失败: {}", e)
        raise HTTPException(400, detail=str(e)) from e
    logger.info("调度任务创建成功, project_id={}, next_run_at={}", body.project_id, job.next_run_at)
    return SchedulerJobInfo(
        project_id=job.project_id,
        repo_url=job.repo_url,
        cron_expr=job.cron_expr,
        branch=job.branch,
        next_run_at=job.next_run_at.isoformat(),
        last_run_at=job.last_run_at.isoformat() if job.last_run_at else None,
        running=job.running,
    )


@router.get("/jobs", response_model=list[SchedulerJobInfo])
async def list_jobs(request: Request) -> list[SchedulerJobInfo]:
    """列出所有调度任务。"""
    logger.debug("收到列出调度任务请求")
    scheduler = _get_scheduler(request)
    jobs = [SchedulerJobInfo(**j) for j in scheduler.list_jobs()]
    logger.debug("返回调度任务列表, 任务数={}", len(jobs))
    return jobs


@router.delete("/jobs/{project_id}", status_code=204)
async def delete_job(project_id: str, request: Request) -> None:
    """删除指定调度任务。"""
    logger.info("收到删除调度任务请求, project_id={}", project_id)
    scheduler = _get_scheduler(request)
    if not scheduler.remove_job(project_id):
        logger.warning("调度任务不存在, project_id={}", project_id)
        raise HTTPException(404, detail=f"调度任务不存在: {project_id}")
    logger.info("调度任务已删除, project_id={}", project_id)


@router.post("/jobs/{project_id}/trigger", status_code=202)
async def trigger_job(project_id: str, request: Request) -> dict:
    """手动触发一次同步。"""
    logger.info("收到手动触发调度任务请求, project_id={}", project_id)
    scheduler = _get_scheduler(request)
    try:
        await scheduler.trigger(project_id)
    except KeyError as e:
        logger.error("触发调度任务失败: 任务不存在, project_id={}", project_id)
        raise HTTPException(404, detail=str(e)) from e
    logger.info("调度任务已触发, project_id={}", project_id)
    return {"detail": f"已触发 {project_id} 同步"}
