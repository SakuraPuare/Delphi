"""上传会话管理：分块上传、断点续传、文件组装"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from delphi.core.cache import get_staging_dir, get_upload_dir, save_to_cache


class HashMismatchError(Exception):
    """组装后的文件哈希与预期不匹配"""


@dataclass
class UploadSession:
    upload_id: str
    project: str
    file_name: str
    file_size: int
    file_hash: str
    total_chunks: int
    pipeline: str  # "doc" | "media"
    received_chunks: set[int]
    created_at: float


_meta_lock = threading.Lock()


def _meta_path(upload_id: str) -> Path:
    """返回会话元数据文件路径。"""
    return get_staging_dir(upload_id) / "meta.json"


def _session_to_dict(session: UploadSession) -> dict:
    """将 UploadSession 序列化为可 JSON 化的字典。"""
    return {
        "upload_id": session.upload_id,
        "project": session.project,
        "file_name": session.file_name,
        "file_size": session.file_size,
        "file_hash": session.file_hash,
        "total_chunks": session.total_chunks,
        "pipeline": session.pipeline,
        "received_chunks": sorted(session.received_chunks),
        "created_at": session.created_at,
    }


def _dict_to_session(data: dict) -> UploadSession:
    """从字典反序列化为 UploadSession。"""
    return UploadSession(
        upload_id=data["upload_id"],
        project=data["project"],
        file_name=data["file_name"],
        file_size=data["file_size"],
        file_hash=data["file_hash"],
        total_chunks=data["total_chunks"],
        pipeline=data["pipeline"],
        received_chunks=set(data.get("received_chunks", [])),
        created_at=data["created_at"],
    )


def _write_meta(session: UploadSession) -> None:
    """线程安全地写入会话元数据。"""
    with _meta_lock:
        path = _meta_path(session.upload_id)
        path.write_text(json.dumps(_session_to_dict(session), ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 会话生命周期
# ---------------------------------------------------------------------------


def create_session(
    project: str,
    file_name: str,
    file_size: int,
    file_hash: str,
    total_chunks: int,
    pipeline: str,
) -> UploadSession:
    """创建上传会话，生成暂存目录并写入 meta.json。"""
    upload_id = uuid.uuid4().hex[:12]
    session = UploadSession(
        upload_id=upload_id,
        project=project,
        file_name=file_name,
        file_size=file_size,
        file_hash=file_hash,
        total_chunks=total_chunks,
        pipeline=pipeline,
        received_chunks=set(),
        created_at=time.time(),
    )

    # get_staging_dir 会自动创建目录和 chunks 子目录
    get_staging_dir(upload_id)
    _write_meta(session)

    logger.info(
        "上传会话已创建, upload_id={}, project={}, file={}, chunks={}",
        upload_id,
        project,
        file_name,
        total_chunks,
    )
    return session


def load_session(upload_id: str) -> UploadSession | None:
    """从暂存目录加载会话，不存在则返回 None。"""
    path = _meta_path(upload_id)
    if not path.exists():
        logger.debug("会话不存在, upload_id={}", upload_id)
        return None
    try:
        data = json.loads(path.read_text())
        session = _dict_to_session(data)
        logger.debug("会话加载成功, upload_id={}, received={}/{}", upload_id, len(session.received_chunks), session.total_chunks)
        return session
    except Exception:
        logger.warning("会话加载失败, upload_id={}", upload_id, exc_info=True)
        return None


def find_session_by_hash(file_hash: str) -> UploadSession | None:
    """扫描所有暂存目录，查找匹配哈希的会话（用于断点续传）。"""
    from delphi.core.config import settings

    staging_root = Path(settings.data_dir) / "cache" / "staging"
    if not staging_root.exists():
        return None

    for meta_file in staging_root.glob("*/meta.json"):
        try:
            data = json.loads(meta_file.read_text())
            if data.get("file_hash") == file_hash:
                session = _dict_to_session(data)
                logger.info("通过哈希找到已有会话, upload_id={}, hash={}", session.upload_id, file_hash[:12])
                return session
        except Exception:
            logger.warning("扫描会话元数据失败, path={}", meta_file, exc_info=True)

    logger.debug("未找到匹配哈希的会话, hash={}", file_hash[:12])
    return None


# ---------------------------------------------------------------------------
# 分块操作
# ---------------------------------------------------------------------------


def save_chunk(upload_id: str, chunk_index: int, data: bytes) -> None:
    """写入分块文件并更新 meta.json 中的 received_chunks。"""
    staging_dir = get_staging_dir(upload_id)
    chunk_path = staging_dir / "chunks" / f"{chunk_index:06d}"
    chunk_path.write_bytes(data)

    session = load_session(upload_id)
    if session is None:
        raise ValueError(f"会话不存在: {upload_id}")

    session.received_chunks.add(chunk_index)
    _write_meta(session)

    logger.debug(
        "分块已保存, upload_id={}, chunk={}, received={}/{}",
        upload_id,
        chunk_index,
        len(session.received_chunks),
        session.total_chunks,
    )


# ---------------------------------------------------------------------------
# 组装与清理
# ---------------------------------------------------------------------------


def assemble(upload_id: str) -> Path:
    """按序拼接所有分块，校验哈希后移入缓存。

    哈希匹配: 调用 cache.save_to_cache，删除暂存目录，返回最终路径。
    哈希不匹配: 抛出 HashMismatchError。
    """
    session = load_session(upload_id)
    if session is None:
        raise ValueError(f"会话不存在: {upload_id}")

    staging_dir = get_staging_dir(upload_id)
    chunks_dir = staging_dir / "chunks"

    # 按序拼接
    assembled = staging_dir / "assembled"
    sha = hashlib.sha256()

    with assembled.open("wb") as out:
        for i in range(session.total_chunks):
            chunk_path = chunks_dir / f"{i:06d}"
            if not chunk_path.exists():
                raise ValueError(f"缺少分块: {i}")
            chunk_data = chunk_path.read_bytes()
            sha.update(chunk_data)
            out.write(chunk_data)

    actual_hash = sha.hexdigest()

    if actual_hash != session.file_hash:
        logger.error(
            "文件哈希不匹配, upload_id={}, expected={}, actual={}",
            upload_id,
            session.file_hash[:12],
            actual_hash[:12],
        )
        raise HashMismatchError(
            f"期望哈希 {session.file_hash}，实际哈希 {actual_hash}"
        )

    # 移入缓存
    final_path = save_to_cache(
        session.project,
        session.file_hash,
        assembled,
        session.file_name,
    )

    # 清理暂存目录
    shutil.rmtree(staging_dir, ignore_errors=True)
    logger.info("文件组装完成, upload_id={}, path={}", upload_id, final_path)

    return final_path


def cleanup_stale(max_age_hours: int = 24) -> int:
    """清理超过指定时间的暂存目录，返回清理数量。"""
    from delphi.core.config import settings

    staging_root = Path(settings.data_dir) / "cache" / "staging"
    if not staging_root.exists():
        return 0

    cutoff = time.time() - max_age_hours * 3600
    removed = 0

    for meta_file in staging_root.glob("*/meta.json"):
        try:
            data = json.loads(meta_file.read_text())
            if data.get("created_at", 0) < cutoff:
                staging_dir = meta_file.parent
                upload_id = data.get("upload_id", staging_dir.name)
                shutil.rmtree(staging_dir, ignore_errors=True)
                removed += 1
                logger.info("已清理过期暂存目录, upload_id={}", upload_id)
        except Exception:
            logger.warning("清理暂存目录失败, path={}", meta_file.parent, exc_info=True)

    logger.info("过期暂存清理完成, 清理数量={}, max_age_hours={}", removed, max_age_hours)
    return removed
