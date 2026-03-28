"""音视频导入流水线"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from delphi.api.websocket import task_manager
from delphi.ingestion.incremental import compute_file_hash, delete_file_chunks, get_existing_hashes
from delphi.ingestion.media_chunker import MEDIA_EXTENSIONS, transcribe_and_chunk
from delphi.ingestion.pipeline import EMBED_BATCH, _task_store, _tasks

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.ingestion.models import Chunk

from loguru import logger

SKIP_NAMES: set[str] = {".DS_Store", "Thumbs.db"}


def _collect_media_files(root: Path, recursive: bool) -> list[Path]:
    """扫描目录中的音视频文件。"""
    logger.debug("扫描媒体目录, root={}, recursive={}", root, recursive)
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
    skip_files: set[str] | None = None,
    *,
    embedding: EmbeddingClient,
    vector_store: VectorStore,
) -> None:
    """音视频导入流水线，作为后台任务运行。"""
    task = _tasks[task_id]
    task["status"] = "running"
    logger.info("开始媒体导入: task={}, project={}", task_id, project)
    task_manager.update_progress(task_id, 0, "开始扫描音视频目录")

    # Persist params for checkpoint/resume
    if _task_store:
        _task_store.save(task_id, {
            **task,
            "type": "media_import",
            "params": {"path": path, "project": project, "recursive": recursive, "whisper_model": whisper_model},
            "updated_at": time.time(),
        })

    try:
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {path}")

        files = _collect_media_files(root, recursive)
        logger.info("收集到媒体文件, 数量={}, 目录={}", len(files), path)
        task_manager.update_progress(task_id, 5, f"收集到 {len(files)} 个媒体文件，计算增量差异")

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

        logger.info("媒体增量差异计算完成, 总文件={}, 变更文件={}, project={}", len(files), len(changed_files), project)

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

        # Skip files already completed in a previous run (checkpoint resume)
        if skip_files:
            changed_files = [f for f in changed_files if str(f.relative_to(root)) not in skip_files]

        task["total"] = len(changed_files)
        if not changed_files:
            logger.info("未检测到变更，跳过媒体导入, project={}", project)
            task["status"] = "done"
            task_manager.complete_task(task_id, {"message": "无变更文件"})
            return

        task_manager.update_progress(task_id, 10, f"发现 {len(changed_files)} 个变更文件，开始转录分块")

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
                logger.warning("媒体转录失败，已跳过: {}", fpath, exc_info=True)
            task["processed"] = i + 1
            task["progress"] = (i + 1) / len(changed_files) if changed_files else 1.0
            chunk_progress = 10 + (i + 1) / len(changed_files) * 50
            task_manager.update_progress(task_id, chunk_progress, f"转录分块: {i + 1}/{len(changed_files)}")

        logger.info("媒体分块生成完成, 总块数={}, 变更文件数={}", len(all_chunks), len(changed_files))

        if not all_chunks:
            task["status"] = "done"
            task_manager.complete_task(task_id, {"message": "无有效分块"})
            return

        task_manager.update_progress(task_id, 60, f"生成 {len(all_chunks)} 个分块，开始 embedding")

        # Group chunks by file for checkpoint tracking
        chunks_by_file: dict[str, list[Chunk]] = {}
        for chunk in all_chunks:
            fp = chunk.metadata.file_path
            chunks_by_file.setdefault(fp, []).append(chunk)

        t0 = time.monotonic()
        completed_files: list[str] = []
        total_embed_files = len(chunks_by_file)
        for file_idx, (file_path, file_chunks) in enumerate(chunks_by_file.items()):
            for i in range(0, len(file_chunks), EMBED_BATCH):
                batch = file_chunks[i:i + EMBED_BATCH]
                texts = [c.text for c in batch]
                result = await embedding.embed_all(texts)
                ids = [uuid.uuid4().hex for _ in batch]
                payloads = [{"text": c.text, **asdict(c.metadata)} for c in batch]
                await vector_store.upsert(project, ids, result.dense, payloads, sparse_vectors=result.sparse or None)

            completed_files.append(file_path)
            if _task_store:
                _task_store.update_checkpoint(task_id, {"phase": "embed", "completed_files": completed_files})

            embed_progress = 60 + (file_idx + 1) / total_embed_files * 35
            task_manager.update_progress(task_id, embed_progress, f"Embedding: {file_idx + 1}/{total_embed_files} 文件")

        elapsed = time.monotonic() - t0
        logger.info("媒体向量嵌入与存储完成, 块数={}, 耗时={:.1f}s", len(all_chunks), elapsed)

        task["status"] = "done"
        logger.info("媒体导入任务完成, task_id={}, 块数={}, 文件数={}", task_id, len(all_chunks), len(changed_files))
        if _task_store:
            _task_store.save(task_id, {**task, "status": "done", "checkpoint": None, "updated_at": time.time()})
        task_manager.complete_task(task_id, {"chunks": len(all_chunks), "files": len(changed_files)})

    except Exception as e:
        logger.error("媒体导入任务失败: {}", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
        if _task_store:
            _task_store.save(task_id, {**task, "status": "failed", "updated_at": time.time()})
        task_manager.fail_task(task_id, str(e))


async def resume_media_import(
    task_id: str,
    *,
    embedding: EmbeddingClient,
    vector_store: VectorStore,
) -> None:
    """从 checkpoint 恢复音视频导入任务。"""
    logger.info("恢复媒体导入任务, task_id={}", task_id)
    if not _task_store:
        raise RuntimeError("TaskStore not available, cannot resume")

    saved = _task_store.load(task_id)
    if saved is None:
        raise ValueError(f"Task '{task_id}' not found in store")

    params = saved.get("params", {})
    checkpoint = saved.get("checkpoint") or {}
    completed_files = set(checkpoint.get("completed_files", []))

    # 重新注册到内存
    _tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "progress": 0.0,
        "total": 0,
        "processed": 0,
        "error": None,
    }
    task_manager.create_task("media_import", task_id=task_id)

    await run_media_import(
        task_id=task_id,
        path=params["path"],
        project=params["project"],
        recursive=params.get("recursive", True),
        whisper_model=params.get("whisper_model", "large-v3"),
        skip_files=completed_files,
        embedding=embedding,
        vector_store=vector_store,
    )
