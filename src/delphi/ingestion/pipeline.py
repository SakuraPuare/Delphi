"""导入任务编排"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from delphi.ingestion.chunker import chunk_file
from delphi.ingestion.git import clone_repo, collect_files
from delphi.ingestion.incremental import compute_file_hash, delete_file_chunks, get_existing_hashes

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.ingestion.models import Chunk

logger = logging.getLogger(__name__)

# In-memory task store (MVP)
_tasks: dict[str, dict] = {}

EMBED_BATCH = 32


def create_task() -> str:
    task_id = uuid.uuid4().hex[:12]
    _tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "total": 0,
        "processed": 0,
        "error": None,
    }
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
) -> None:
    """Full git import pipeline. Runs as a background task."""
    task = _tasks[task_id]
    task["status"] = "running"
    tmp_dir = None

    try:
        # 1. Clone
        is_local = not url.startswith(("http://", "https://", "git@", "ssh://"))
        if is_local:
            repo_path = Path(url)
            if not repo_path.exists():
                raise FileNotFoundError(f"路径不存在: {url}")
        else:
            tmp_dir = Path(tempfile.mkdtemp(prefix="delphi-"))
            repo_path = tmp_dir / "repo"
            await clone_repo(url, repo_path, branch=branch, depth=depth)

        # 2. Collect files
        files = collect_files(repo_path, include=include, exclude=exclude)
        logger.info("Collected %d files from %s", len(files), url)

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

        task["total"] = len(changed_files)
        if not changed_files:
            logger.info("No changes detected, skipping import for %s", project)
            task["status"] = "done"
            return

        # 4. Parse & chunk (only changed files)
        all_chunks: list[Chunk] = []
        for i, fpath in enumerate(changed_files):
            try:
                rel_path = fpath.relative_to(repo_path)
                chunks = chunk_file(fpath, repo_url=url)
                current_hash = file_hash_map[str(rel_path)]
                for c in chunks:
                    c.metadata.file_path = str(rel_path)
                    c.metadata.file_hash = current_hash
                all_chunks.extend(chunks)
            except Exception:
                logger.warning("Failed to parse %s, skipping", fpath, exc_info=True)
            task["processed"] = i + 1
            task["progress"] = (i + 1) / len(changed_files) if changed_files else 1.0

        logger.info("Generated %d chunks from %d changed files", len(all_chunks), len(changed_files))

        if not all_chunks:
            task["status"] = "done"
            return

        # 5. Embed & upsert in batches (dense + sparse)
        t0 = time.monotonic()
        for i in range(0, len(all_chunks), EMBED_BATCH):
            batch = all_chunks[i : i + EMBED_BATCH]
            texts = [c.text for c in batch]
            result = await embedding.embed_all(texts)

            ids = [uuid.uuid4().hex for _ in batch]
            payloads = [{"text": c.text, **asdict(c.metadata)} for c in batch]
            await vector_store.upsert(project, ids, result.dense, payloads, sparse_vectors=result.sparse or None)

        elapsed = time.monotonic() - t0
        logger.info("Embedded & stored %d chunks in %.1fs", len(all_chunks), elapsed)

        task["status"] = "done"

    except Exception as e:
        logger.error("Import failed: %s", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)

    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
