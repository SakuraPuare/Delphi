"""导入任务编排"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from delphi.api.websocket import task_manager
from delphi.core.task_store import TaskStore  # noqa: TC001
from delphi.core.telemetry import get_tracer
from delphi.ingestion.chunker import chunk_file
from delphi.ingestion.doc_chunker import chunk_doc_file
from delphi.ingestion.git import clone_or_fetch, collect_files
from delphi.ingestion.incremental import compute_file_hash, delete_file_chunks, get_existing_hashes

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.ingestion.models import Chunk

from loguru import logger

_tracer = get_tracer(__name__)

# In-memory task store (MVP) — 保留兼容性，同时同步到 TaskManager
_tasks: dict[str, dict] = {}

# 可选持久化存储，用于 checkpoint/resume（由 app startup 注入）
_task_store: TaskStore | None = None

EMBED_BATCH = 32


def set_task_store(store: TaskStore) -> None:
    """设置持久化存储实例，应在应用启动时调用"""
    global _task_store
    _task_store = store
    logger.info("TaskStore 已注入, store_type={}", type(store).__name__)


def create_task(task_type: str = "import", params: dict | None = None) -> str:
    task_id = uuid.uuid4().hex[:12]
    logger.info("创建导入任务, task_id={}, task_type={}", task_id, task_type)
    _tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "total": 0,
        "processed": 0,
        "error": None,
    }
    task_manager.create_task(task_type, task_id=task_id)
    if _task_store:
        _task_store.save(
            task_id,
            {
                "task_id": task_id,
                "task_type": task_type,
                "status": "pending",
                "progress": 0.0,
                "params": params,
                "checkpoint": None,
                "result": None,
                "error": None,
                "created_at": time.time(),
                "updated_at": time.time(),
            },
        )
        logger.debug("任务已持久化到 TaskStore, task_id={}", task_id)
    return task_id


def get_task(task_id: str) -> dict | None:
    return _tasks.get(task_id)


async def run_git_import(
    task_id: str,
    url: str,
    project: str,
    branch: str = "main",
    depth: int = 1,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    *,
    embedding: EmbeddingClient,
    vector_store: VectorStore,
    skip_files: set[str] | None = None,
) -> None:
    """Full git import pipeline. Runs as a background task."""
    task = _tasks[task_id]
    task["status"] = "running"
    logger.info("开始 Git 导入任务, task_id={}, url={}, project={}, branch={}", task_id, url, project, branch)
    task_manager.update_progress(task_id, 0, "开始克隆仓库")

    try:
        # 1. Clone
        with _tracer.start_as_current_span("pipeline.git_clone") as clone_span:
            clone_span.set_attribute("pipeline.url", url)
            clone_span.set_attribute("pipeline.branch", branch)
            is_local = not url.startswith(("http://", "https://", "git@", "ssh://"))
            if is_local:
                repo_path = Path(url)
                if not repo_path.exists():
                    raise FileNotFoundError(f"路径不存在: {url}")
            else:
                repo_path = await clone_or_fetch(url, project, branch=branch, depth=depth)

        task_manager.update_progress(task_id, 5, "仓库克隆完成，收集文件中")

        # 2. Collect files
        files = collect_files(repo_path, include=include, exclude=exclude)
        logger.info("收集到文件, 数量={}, 仓库={}", len(files), url)

        task_manager.update_progress(task_id, 10, f"收集到 {len(files)} 个文件，计算增量差异")

        # 3. Incremental: compute hashes & diff against existing
        await vector_store.ensure_collection(project)
        existing_hashes = await get_existing_hashes(vector_store, project)

        file_hash_map: dict[str, str] = {}  # rel_path -> hash
        for fpath in files:
            rel_path = str(fpath.relative_to(repo_path))
            file_hash_map[rel_path] = compute_file_hash(fpath)

        # Find changed or new files
        changed_files: list[Path] = []
        for fpath in files:
            rel_path = str(fpath.relative_to(repo_path))
            current_hash = file_hash_map[rel_path]
            existing = existing_hashes.get(rel_path, set())
            if current_hash not in existing:
                changed_files.append(fpath)

        logger.info("增量差异计算完成, 总文件={}, 变更文件={}, project={}", len(files), len(changed_files), project)

        # Delete chunks for files that no longer exist
        current_paths = set(file_hash_map.keys())
        for old_path in existing_hashes:
            if old_path not in current_paths:
                await delete_file_chunks(vector_store, project, old_path)

        # Delete old chunks for changed files (will be re-created below)
        for fpath in changed_files:
            rel_path = str(fpath.relative_to(repo_path))
            if rel_path in existing_hashes:
                await delete_file_chunks(vector_store, project, rel_path)

        # 跳过已完成的文件（断点恢复场景）
        if skip_files:
            changed_files = [f for f in changed_files if str(f.relative_to(repo_path)) not in skip_files]

        task["total"] = len(changed_files)
        if not changed_files:
            logger.info("未检测到变更，跳过导入, project={}", project)
            task["status"] = "done"
            task_manager.complete_task(task_id, {"message": "无变更文件"})
            return

        task_manager.update_progress(task_id, 15, f"发现 {len(changed_files)} 个变更文件，开始解析分块")

        # 4. Parse & chunk (only changed files)
        with _tracer.start_as_current_span("pipeline.parse_chunk") as pc_span:
            pc_span.set_attribute("pipeline.num_changed_files", len(changed_files))
            all_chunks: list[Chunk] = []
            for i, fpath in enumerate(changed_files):
                try:
                    rel_path = fpath.relative_to(repo_path)
                    # 文档文件使用 doc chunker，代码文件使用 code chunker
                    _DOC_EXTS = {".md", ".mdx", ".txt", ".rst"}
                    if fpath.suffix.lower() in _DOC_EXTS:
                        chunks = chunk_doc_file(fpath)
                    else:
                        chunks = chunk_file(fpath, repo_url=url)
                    current_hash = file_hash_map[str(rel_path)]
                    for c in chunks:
                        c.metadata.file_path = str(rel_path)
                        c.metadata.file_hash = current_hash
                    all_chunks.extend(chunks)
                except Exception:
                    logger.warning("文件解析失败，已跳过: {}", fpath, exc_info=True)
                task["processed"] = i + 1
                task["progress"] = (i + 1) / len(changed_files) if changed_files else 1.0
                # 解析阶段占 15%-60%
                chunk_progress = 15 + (i + 1) / len(changed_files) * 45
                task_manager.update_progress(task_id, chunk_progress, f"解析分块: {i + 1}/{len(changed_files)}")
            pc_span.set_attribute("pipeline.num_chunks", len(all_chunks))

        logger.info("分块生成完成, 总块数={}, 变更文件数={}", len(all_chunks), len(changed_files))

        if not all_chunks:
            task["status"] = "done"
            task_manager.complete_task(task_id, {"message": "无有效分块"})
            return

        task_manager.update_progress(task_id, 60, f"生成 {len(all_chunks)} 个分块，开始 embedding")

        # 5. Embed & upsert per-file (支持 checkpoint)
        with _tracer.start_as_current_span("pipeline.embed_store") as es_span:
            es_span.set_attribute("pipeline.num_chunks", len(all_chunks))
            t0 = time.monotonic()

            # 按文件分组
            chunks_by_file: dict[str, list[Chunk]] = {}
            for chunk in all_chunks:
                fp = chunk.metadata.file_path
                chunks_by_file.setdefault(fp, []).append(chunk)

            completed_files: list[str] = []
            total_files = len(chunks_by_file)
            for file_idx, (file_path, file_chunks) in enumerate(chunks_by_file.items()):
                for i in range(0, len(file_chunks), EMBED_BATCH):
                    batch = file_chunks[i : i + EMBED_BATCH]
                    texts = [c.text for c in batch]
                    result = await embedding.embed_all(texts)
                    ids = [uuid.uuid4().hex for _ in batch]
                    payloads = [{"text": c.text, **asdict(c.metadata)} for c in batch]
                    await vector_store.upsert(
                        project, ids, result.dense, payloads, sparse_vectors=result.sparse or None
                    )

                completed_files.append(file_path)
                if _task_store:
                    _task_store.update_checkpoint(task_id, {"phase": "embed", "completed_files": completed_files})

                # embedding 阶段占 60%-95%
                embed_progress = 60 + (file_idx + 1) / total_files * 35
                task_manager.update_progress(task_id, embed_progress, f"Embedding: {file_idx + 1}/{total_files} 文件")

            elapsed = time.monotonic() - t0
            es_span.set_attribute("pipeline.embed_store.latency_s", round(elapsed, 2))
            logger.info("向量嵌入与存储完成, 块数={}, 耗时={:.1f}s", len(all_chunks), elapsed)

        task["status"] = "done"
        logger.info("Git 导入任务完成, task_id={}, 块数={}, 文件数={}", task_id, len(all_chunks), len(changed_files))
        task_manager.complete_task(task_id, {"chunks": len(all_chunks), "files": len(changed_files)})
        if _task_store:
            data = {**_tasks[task_id], "status": "done", "checkpoint": None, "updated_at": time.time()}
            _task_store.save(task_id, data)

    except Exception as e:
        logger.error("导入任务失败: {}", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
        task_manager.fail_task(task_id, str(e))
        if _task_store:
            _task_store.save(task_id, {**_tasks[task_id], "status": "failed", "updated_at": time.time()})


async def resume_git_import(
    task_id: str,
    *,
    embedding: EmbeddingClient,
    vector_store: VectorStore,
) -> None:
    """从断点恢复 git 导入任务"""
    logger.info("恢复 Git 导入任务, task_id={}", task_id)
    if not _task_store:
        raise RuntimeError("TaskStore not initialized")

    task_data = _task_store.load(task_id)
    if not task_data:
        raise ValueError(f"Task {task_id} not found")

    params = task_data.get("params") or {}
    checkpoint = task_data.get("checkpoint") or {}
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
    task_manager.create_task(params.get("task_type", "git_import"), task_id=task_id)

    await run_git_import(
        task_id,
        url=params["url"],
        project=params["project"],
        branch=params.get("branch", "main"),
        depth=params.get("depth", 1),
        include=params.get("include"),
        exclude=params.get("exclude"),
        embedding=embedding,
        vector_store=vector_store,
        skip_files=completed_files,
    )
