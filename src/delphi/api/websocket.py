"""WebSocket 任务进度推送管理"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import StrEnum
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class TaskRecord:
    """单个任务的状态记录"""

    __slots__ = (
        "task_id",
        "task_type",
        "status",
        "progress",
        "message",
        "metadata",
        "result",
        "error",
        "created_at",
        "updated_at",
    )

    def __init__(self, task_id: str, task_type: str, metadata: dict[str, Any] | None = None) -> None:
        self.task_id = task_id
        self.task_type = task_type
        self.status = TaskStatus.PENDING
        self.progress: float = 0.0
        self.message: str = ""
        self.metadata: dict[str, Any] = metadata or {}
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.created_at: float = time.time()
        self.updated_at: float = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "metadata": self.metadata,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskManager:
    """管理所有运行中的任务，并通过 asyncio 广播机制通知 WebSocket 连接。"""

    _instance: TaskManager | None = None

    def __new__(cls) -> TaskManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._tasks: dict[str, TaskRecord] = {}
        # task_id -> set of asyncio.Queue (每个 WebSocket 连接一个)
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        # 订阅所有任务的全局队列
        self._global_subscribers: set[asyncio.Queue] = set()

    # ---- 任务生命周期 ----

    def create_task(
        self,
        task_type: str,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """创建任务记录并返回 task_id。"""
        if task_id is None:
            task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(task_id, task_type, metadata)
        self._tasks[task_id] = record
        self._broadcast(task_id, {"event": "created", **record.to_dict()})
        return task_id

    def update_progress(self, task_id: str, progress: float, message: str = "") -> None:
        """更新任务进度 (0-100)。"""
        record = self._tasks.get(task_id)
        if record is None:
            return
        record.progress = min(progress, 100.0)
        record.message = message
        record.status = TaskStatus.RUNNING
        record.updated_at = time.time()
        self._broadcast(task_id, {"event": "progress", **record.to_dict()})

    def complete_task(self, task_id: str, result: dict[str, Any] | None = None) -> None:
        """标记任务完成。"""
        record = self._tasks.get(task_id)
        if record is None:
            return
        record.status = TaskStatus.DONE
        record.progress = 100.0
        record.result = result
        record.updated_at = time.time()
        self._broadcast(task_id, {"event": "completed", **record.to_dict()})

    def fail_task(self, task_id: str, error: str) -> None:
        """标记任务失败。"""
        record = self._tasks.get(task_id)
        if record is None:
            return
        record.status = TaskStatus.FAILED
        record.error = error
        record.updated_at = time.time()
        self._broadcast(task_id, {"event": "failed", **record.to_dict()})

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态。"""
        record = self._tasks.get(task_id)
        return record.to_dict() if record else None

    def list_tasks(self) -> list[dict[str, Any]]:
        """列出所有任务。"""
        return [r.to_dict() for r in self._tasks.values()]

    # ---- 广播 & 订阅 ----

    def _broadcast(self, task_id: str, payload: dict[str, Any]) -> None:
        """向所有订阅该任务和全局订阅者推送消息。"""
        queues: set[asyncio.Queue] = set()
        queues.update(self._global_subscribers)
        queues.update(self._subscribers.get(task_id, set()))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("WebSocket subscriber queue full, dropping message for task %s", task_id)

    def subscribe(self, task_id: str | None = None) -> asyncio.Queue:
        """订阅任务更新，返回一个 Queue。task_id=None 表示订阅全部。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        if task_id is None:
            self._global_subscribers.add(q)
        else:
            self._subscribers.setdefault(task_id, set()).add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue, task_id: str | None = None) -> None:
        """取消订阅。"""
        if task_id is None:
            self._global_subscribers.discard(q)
        else:
            subs = self._subscribers.get(task_id)
            if subs:
                subs.discard(q)
                if not subs:
                    del self._subscribers[task_id]


# 模块级单例
task_manager = TaskManager()


# ---- WebSocket 端点处理函数 ----


async def ws_all_tasks(websocket: WebSocket) -> None:
    """处理 /ws/tasks 连接：订阅所有任务进度。"""
    await websocket.accept()
    mgr = task_manager

    # 连接后立即推送当前所有任务状态
    for task_data in mgr.list_tasks():
        await websocket.send_json({"event": "snapshot", **task_data})

    q = mgr.subscribe(task_id=None)
    try:
        while True:
            payload = await q.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket /ws/tasks connection closed", exc_info=True)
    finally:
        mgr.unsubscribe(q, task_id=None)


async def ws_single_task(websocket: WebSocket, task_id: str) -> None:
    """处理 /ws/tasks/{task_id} 连接：订阅特定任务进度。"""
    await websocket.accept()
    mgr = task_manager

    # 连接后立即推送当前任务状态
    current = mgr.get_task(task_id)
    if current:
        await websocket.send_json({"event": "snapshot", **current})

    q = mgr.subscribe(task_id=task_id)
    try:
        while True:
            payload = await q.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket /ws/tasks/%s connection closed", task_id, exc_info=True)
    finally:
        mgr.unsubscribe(q, task_id=task_id)
