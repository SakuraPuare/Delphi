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
        task["total"] = len(files)
        logger.info("Collected %d files from %s", len(files), url)

        # 3. Parse & chunk
        all_chunks: list[Chunk] = []
        for i, fpath in enumerate(files):
            try:
                rel_path = fpath.relative_to(repo_path)
                chunks = chunk_file(fpath, repo_url=url)
                # Normalize file_path to relative
                for c in chunks:
                    c.metadata.file_path = str(rel_path)
                all_chunks.extend(chunks)
            except Exception:
                logger.warning("Failed to parse %s, skipping", fpath, exc_info=True)
            task["processed"] = i + 1
            task["progress"] = (i + 1) / len(files) if files else 1.0

        logger.info("Generated %d chunks from %d files", len(all_chunks), len(files))

        if not all_chunks:
            task["status"] = "done"
            return

        # 4. Ensure collection
        await vector_store.ensure_collection(project)

        # 5. Embed & upsert in batches
        t0 = time.monotonic()
        for i in range(0, len(all_chunks), EMBED_BATCH):
            batch = all_chunks[i : i + EMBED_BATCH]
            texts = [c.text for c in batch]
            vectors = await embedding.embed(texts)

            ids = [uuid.uuid4().hex for _ in batch]
            payloads = [{"text": c.text, **asdict(c.metadata)} for c in batch]
            await vector_store.upsert(project, ids, vectors, payloads)

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
