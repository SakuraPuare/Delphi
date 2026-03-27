"""音视频导入流水线"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from delphi.ingestion.incremental import compute_file_hash, delete_file_chunks, get_existing_hashes
from delphi.ingestion.media_chunker import MEDIA_EXTENSIONS, transcribe_and_chunk
from delphi.ingestion.pipeline import EMBED_BATCH, _tasks

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.ingestion.models import Chunk

logger = logging.getLogger(__name__)

SKIP_NAMES: set[str] = {".DS_Store", "Thumbs.db"}


def _collect_media_files(root: Path, recursive: bool) -> list[Path]:
    """扫描目录中的音视频文件。"""
    pattern = "**/*" if recursive else "*"
    result: list[Path] = []

    for p in root.glob(pattern):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        if p.name in SKIP_NAMES:
            continue
        if p.suffix.lower() in MEDIA_EXTENSIONS:
            result.append(p)

    return sorted(result)


async def run_media_import(
    task_id: str,
    path: str,
    project: str,
    recursive: bool = True,
    whisper_model: str = "large-v3",
    *,
    embedding: EmbeddingClient,
    vector_store: VectorStore,
) -> None:
    """音视频导入流水线，作为后台任务运行。"""
    task = _tasks[task_id]
    task["status"] = "running"

    try:
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {path}")

        files = _collect_media_files(root, recursive)
        logger.info("Collected %d media files from %s", len(files), path)

        # 增量更新：计算 hash 并与已有数据对比
        await vector_store.ensure_collection(project)
        existing_hashes = await get_existing_hashes(vector_store, project)

        file_hash_map: dict[str, str] = {}
        for fpath in files:
            rel_path = str(fpath.relative_to(root))
            file_hash_map[rel_path] = compute_file_hash(fpath)

        # 找出变更或新增的文件
        changed_files: list[Path] = []
        for fpath in files:
            rel_path = str(fpath.relative_to(root))
            current_hash = file_hash_map[rel_path]
            existing = existing_hashes.get(rel_path, set())
            if current_hash not in existing:
                changed_files.append(fpath)

        # 删除已不存在的文件的 chunks
        current_paths = set(file_hash_map.keys())
        for old_path in existing_hashes:
            if old_path not in current_paths:
                await delete_file_chunks(vector_store, project, old_path)

        # 删除变更文件的旧 chunks
        for fpath in changed_files:
            rel_path = str(fpath.relative_to(root))
            if rel_path in existing_hashes:
                await delete_file_chunks(vector_store, project, rel_path)

        task["total"] = len(changed_files)
        if not changed_files:
            logger.info("No changes detected, skipping media import for %s", project)
            task["status"] = "done"
            return

        # 转录 & 切分
        all_chunks: list[Chunk] = []
        for i, fpath in enumerate(changed_files):
            try:
                rel_path = fpath.relative_to(root)
                chunks = transcribe_and_chunk(fpath, model_size=whisper_model)
                current_hash = file_hash_map[str(rel_path)]
                for c in chunks:
                    c.metadata.file_path = str(rel_path)
                    c.metadata.file_hash = current_hash
                all_chunks.extend(chunks)
            except Exception:
                logger.warning("Failed to transcribe %s, skipping", fpath, exc_info=True)
            task["processed"] = i + 1
            task["progress"] = (i + 1) / len(changed_files) if changed_files else 1.0

        logger.info("Generated %d chunks from %d changed media files", len(all_chunks), len(changed_files))

        if not all_chunks:
            task["status"] = "done"
            return

        # Embed & 入库
        t0 = time.monotonic()
        for i in range(0, len(all_chunks), EMBED_BATCH):
            batch = all_chunks[i : i + EMBED_BATCH]
            texts = [c.text for c in batch]
            result = await embedding.embed_all(texts)

            ids = [uuid.uuid4().hex for _ in batch]
            payloads = [{"text": c.text, **asdict(c.metadata)} for c in batch]
            await vector_store.upsert(project, ids, result.dense, payloads, sparse_vectors=result.sparse)

        elapsed = time.monotonic() - t0
        logger.info("Embedded & stored %d media chunks in %.1fs", len(all_chunks), elapsed)

        task["status"] = "done"

    except Exception as e:
        logger.error("Media import failed: %s", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
