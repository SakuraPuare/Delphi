"""任务持久化存储：JSON 文件 + 线程安全"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from loguru import logger

from delphi.core.config import settings


class TaskStore:
    """管理可恢复任务的持久化存储"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._task_dir = Path(settings.data_dir) / "tasks"
        self._task_dir.mkdir(parents=True, exist_ok=True)
        logger.info("TaskStore 初始化完成, 存储目录={}", self._task_dir)

    def _path(self, task_id: str) -> Path:
        return self._task_dir / f"{task_id}.json"

    def save(self, task_id: str, data: dict) -> None:
        """写入或更新任务 JSON 文件"""
        with self._lock:
            path = self._path(task_id)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("任务已保存, task_id={}", task_id)

    def load(self, task_id: str) -> dict | None:
        """读取单个任务，不存在则返回 None"""
        path = self._path(task_id)
        if not path.exists():
            logger.debug("任务文件不存在, task_id={}", task_id)
            return None
        try:
            data = json.loads(path.read_text())
            logger.debug("任务加载成功, task_id={}, status={}", task_id, data.get("status"))
            return data
        except Exception:
            logger.warning("任务加载失败, task_id={}", task_id, exc_info=True)
            return None

    def list_resumable(self) -> list[dict]:
        """列出可恢复的任务（状态为 running 或 failed）"""
        tasks = [task for task in self.list_all() if task.get("status") in ("running", "failed")]
        logger.info("可恢复任务数={}", len(tasks))
        return tasks

    def list_all(self) -> list[dict]:
        """列出所有任务"""
        tasks: list[dict] = []
        for p in self._task_dir.glob("*.json"):
            try:
                tasks.append(json.loads(p.read_text()))
            except Exception:
                logger.warning("读取任务文件失败, file={}", p.name, exc_info=True)
        logger.debug("列出全部任务, 总数={}", len(tasks))
        return tasks

    def delete(self, task_id: str) -> None:
        """删除任务文件"""
        with self._lock:
            path = self._path(task_id)
            if path.exists():
                path.unlink()
                logger.info("任务已删除, task_id={}", task_id)
            else:
                logger.debug("任务文件不存在, 跳过删除, task_id={}", task_id)

    def update_checkpoint(self, task_id: str, checkpoint: dict) -> None:
        """更新任务的 checkpoint 字段和 updated_at 时间戳"""
        with self._lock:
            path = self._path(task_id)
            if not path.exists():
                logger.warning("任务不存在, 跳过 checkpoint 更新, task_id={}", task_id)
                return
            try:
                data = json.loads(path.read_text())
                data["checkpoint"] = checkpoint
                data["updated_at"] = time.time()
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
                logger.info("checkpoint 已更新, task_id={}", task_id)
            except Exception:
                logger.warning("checkpoint 更新失败, task_id={}", task_id, exc_info=True)
