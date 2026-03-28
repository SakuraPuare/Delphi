"""基于 asyncio 的轻量级定时同步调度器。"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from delphi.scheduler.cron import CronExpr, next_run, parse_cron

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore


@dataclass
class SyncJob:
    """单个定时同步任务的描述。"""

    project_id: str
    repo_url: str
    cron_expr: str
    branch: str = "main"
    cron: CronExpr = field(init=False, repr=False)
    next_run_at: datetime = field(init=False)
    last_run_at: datetime | None = field(default=None, init=False)
    running: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.cron = parse_cron(self.cron_expr)
        self.next_run_at = next_run(self.cron, datetime.now())


class SyncScheduler:
    """基于 asyncio 的定时同步调度器。

    不依赖 APScheduler 等第三方库，通过 asyncio.sleep 实现定时轮询。
    """

    def __init__(self, embedding: EmbeddingClient, vector_store: VectorStore) -> None:
        self._embedding = embedding
        self._vector_store = vector_store
        self._jobs: dict[str, SyncJob] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Job 管理
    # ------------------------------------------------------------------

    def add_job(
        self,
        project_id: str,
        repo_url: str,
        cron_expr: str,
        branch: str = "main",
    ) -> SyncJob:
        """添加定时同步任务。如果 project_id 已存在则覆盖。"""
        job = SyncJob(project_id=project_id, repo_url=repo_url, cron_expr=cron_expr, branch=branch)
        self._jobs[project_id] = job
        logger.info(
            "调度任务已添加: project={}, cron={}, branch={}, 下次执行={}",
            project_id,
            cron_expr,
            branch,
            job.next_run_at,
        )
        return job

    def remove_job(self, project_id: str) -> bool:
        """移除任务，返回是否成功。"""
        removed = self._jobs.pop(project_id, None)
        if removed:
            logger.info("调度任务已移除: project={}", project_id)
        else:
            logger.warning("调度任务移除失败, 不存在: project={}", project_id)
        return removed is not None

    def list_jobs(self) -> list[dict]:
        """列出所有调度任务的摘要信息。"""
        return [
            {
                "project_id": j.project_id,
                "repo_url": j.repo_url,
                "cron_expr": j.cron_expr,
                "branch": j.branch,
                "next_run_at": j.next_run_at.isoformat(),
                "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
                "running": j.running,
            }
            for j in self._jobs.values()
        ]

    # ------------------------------------------------------------------
    # 调度循环
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动调度器后台任务。"""
        if self._task is not None and not self._task.done():
            logger.warning("调度器已在运行中, 忽略重复启动")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("调度器已启动, 当前注册任务数={}", len(self._jobs))

    async def stop(self) -> None:
        """停止调度器并等待后台任务结束。"""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("调度器已停止")

    async def trigger(self, project_id: str) -> None:
        """手动触发一次指定项目的同步。"""
        job = self._jobs.get(project_id)
        if job is None:
            logger.warning("手动触发失败, 调度任务不存在: project={}", project_id)
            raise KeyError(f"调度任务不存在: {project_id}")
        logger.info("手动触发同步: project={}", project_id)
        await self._execute(job)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """主调度循环，每 30 秒检查一次是否有任务需要执行。"""
        logger.info("调度循环启动, 已注册 {} 个任务", len(self._jobs))
        while not self._stop_event.is_set():
            now = datetime.now()
            for job in list(self._jobs.values()):
                if job.running:
                    continue
                if now >= job.next_run_at:
                    asyncio.create_task(self._execute(job))
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30)
                break  # stop_event 被设置
            except TimeoutError:
                pass  # 正常超时，继续循环

    async def _execute(self, job: SyncJob) -> None:
        """执行一次增量同步。"""
        from delphi.ingestion.pipeline import create_task, run_git_import

        job.running = True
        task_id = create_task()
        logger.info(
            "调度任务触发: project={}, task_id={}, repo={}, branch={}",
            job.project_id,
            task_id,
            job.repo_url,
            job.branch,
        )

        try:
            await run_git_import(
                task_id=task_id,
                url=job.repo_url,
                project=job.project_id,
                branch=job.branch,
                embedding=self._embedding,
                vector_store=self._vector_store,
            )
            logger.info("调度同步完成: project={}, task_id={}", job.project_id, task_id)
        except Exception:
            logger.error("调度同步失败: project={}, task_id={}", job.project_id, task_id, exc_info=True)
        finally:
            job.running = False
            job.last_run_at = datetime.now()
            job.next_run_at = next_run(job.cron, datetime.now())
            logger.debug("下次执行时间更新: project={}, next_run_at={}", job.project_id, job.next_run_at)
