"""缓存目录管理：上传文件、暂存区、Git 仓库的统一路径规划"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from loguru import logger

from delphi.core.config import settings


def _cache_root() -> Path:
    """返回缓存根目录 {data_dir}/cache/"""
    return Path(settings.data_dir) / "cache"


# ---------------------------------------------------------------------------
# 上传缓存
# ---------------------------------------------------------------------------


def get_upload_dir(project: str) -> Path:
    """返回项目的上传缓存目录，不存在则自动创建。

    路径: {data_dir}/cache/uploads/{project}/
    """
    d = _cache_root() / "uploads" / project
    d.mkdir(parents=True, exist_ok=True)
    logger.debug("获取上传缓存目录, project={}, path={}", project, d)
    return d


def check_cache(project: str, file_hash: str) -> Path | None:
    """检查文件是否已缓存，存在则返回路径，否则返回 None。"""
    cached = get_upload_dir(project) / file_hash
    if cached.exists():
        logger.debug("缓存命中, project={}, hash={}", project, file_hash[:12])
        return cached
    logger.debug("缓存未命中, project={}, hash={}", project, file_hash[:12])
    return None


def save_to_cache(
    project: str,
    file_hash: str,
    src_path: Path,
    original_name: str,
) -> Path:
    """将文件移入缓存并写入 .meta 侧车文件，返回最终缓存路径。"""
    upload_dir = get_upload_dir(project)
    dest = upload_dir / file_hash

    shutil.move(str(src_path), str(dest))

    meta = {
        "name": original_name,
        "size": dest.stat().st_size,
        "uploaded_at": time.time(),
    }
    meta_path = upload_dir / f"{file_hash}.meta"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    logger.info(
        "文件已缓存, project={}, hash={}, name={}, size={}",
        project,
        file_hash[:12],
        original_name,
        meta["size"],
    )
    return dest


def list_cached_files(project: str) -> list[dict]:
    """列出项目下所有已缓存文件及其元数据。"""
    upload_dir = get_upload_dir(project)
    result: list[dict] = []

    for meta_path in upload_dir.glob("*.meta"):
        file_hash = meta_path.stem
        try:
            meta = json.loads(meta_path.read_text())
            meta["file_hash"] = file_hash
            result.append(meta)
        except Exception:
            logger.warning("读取缓存元数据失败, meta_path={}", meta_path, exc_info=True)

    logger.debug("列出缓存文件, project={}, 数量={}", project, len(result))
    return result


# ---------------------------------------------------------------------------
# 暂存区（分块上传）
# ---------------------------------------------------------------------------


def get_staging_dir(upload_id: str) -> Path:
    """返回上传会话的暂存目录，同时创建 chunks 子目录。

    路径: {data_dir}/cache/staging/{upload_id}/
    """
    d = _cache_root() / "staging" / upload_id
    (d / "chunks").mkdir(parents=True, exist_ok=True)
    logger.debug("获取暂存目录, upload_id={}, path={}", upload_id, d)
    return d


# ---------------------------------------------------------------------------
# Git 仓库缓存
# ---------------------------------------------------------------------------


def get_repo_dir(project: str, url: str) -> Path:
    """返回 Git 仓库的缓存目录，不存在则自动创建。

    路径: {data_dir}/cache/repos/{project}/{sha256(url)[:16]}/
    使用 URL 的 SHA-256 前 16 位作为安全目录名。
    """
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    d = _cache_root() / "repos" / project / url_hash
    d.mkdir(parents=True, exist_ok=True)
    logger.debug("获取仓库缓存目录, project={}, url={}, path={}", project, url, d)
    return d
