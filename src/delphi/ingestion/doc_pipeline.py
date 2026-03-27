"""文档目录导入流水线"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from delphi.ingestion.doc_chunker import chunk_doc_file
from delphi.ingestion.incremental import compute_file_hash, delete_file_chunks, get_existing_hashes
from delphi.ingestion.pipeline import EMBED_BATCH, _tasks

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.ingestion.models import Chunk

logger = logging.getLogger(__name__)

SKIP_NAMES: set[str] = {".DS_Store", "Thumbs.db"}


def _collect_doc_files(root: Path, recursive: bool, file_types: list[str]) -> list[Path]:
    """Walk directory and return matching document files."""
    exts = {"." + ft.lstrip(".").lower() for ft in file_types}
    pattern = "**/*" if recursive else "*"
    result: list[Path] = []

    for p in root.glob(pattern):
        if not p.is_file():
            continue
        # Skip hidden files/dirs
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        # Skip system files
        if p.name in SKIP_NAMES:
            continue
        if p.suffix.lower() in exts:
            result.append(p)

    return sorted(result)


async def run_doc_import(
    task_id: str,
    path: str,
    project: str,
    recursive: bool = True,
    file_types: list[str] | None = None,
    *,
    embedding: EmbeddingClient,
    vector_store: VectorStore,
) -> None:
    """Full doc import pipeline. Runs as a background task."""
    task = _tasks[task_id]
    task["status"] = "running"

    if file_types is None:
        file_types = ["md", "txt"]

    try:
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {path}")

        files = _collect_doc_files(root, recursive, file_types)
        logger.info("Collected %d doc files from %s", len(files), path)

        # Incremental: compute hashes & diff against existing
        await vector_store.ensure_collection(project)
        existing_hashes = await get_existing_hashes(vector_store, project)

        file_hash_map: dict[str, str] = {}  # rel_path -> hash
        for fpath in files:
            rel_path = str(fpath.relative_to(root))
            file_hash_map[rel_path] = compute_file_hash(fpath)

        # Find changed or new files
        changed_files: list[Path] = []
        for fpath in files:
            rel_path = str(fpath.relative_to(root))
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
            rel_path = str(fpath.relative_to(root))
            if rel_path in existing_hashes:
                await delete_file_chunks(vector_store, project, rel_path)

        task["total"] = len(changed_files)
        if not changed_files:
            logger.info("No changes detected, skipping doc import for %s", project)
            task["status"] = "done"
            return

        all_chunks: list[Chunk] = []
        for i, fpath in enumerate(changed_files):
            try:
                rel_path = fpath.relative_to(root)
                chunks = chunk_doc_file(fpath)
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

        t0 = time.monotonic()
        for i in range(0, len(all_chunks), EMBED_BATCH):
            batch = all_chunks[i : i + EMBED_BATCH]
            texts = [c.text for c in batch]
            result = await embedding.embed_all(texts)

            ids = [uuid.uuid4().hex for _ in batch]
            payloads = [{"text": c.text, **asdict(c.metadata)} for c in batch]
            await vector_store.upsert(project, ids, result.dense, payloads, sparse_vectors=result.sparse)

        elapsed = time.monotonic() - t0
        logger.info("Embedded & stored %d chunks in %.1fs", len(all_chunks), elapsed)

        task["status"] = "done"

    except Exception as e:
        logger.error("Doc import failed: %s", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
