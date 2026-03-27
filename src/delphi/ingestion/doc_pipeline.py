"""文档目录导入流水线"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from delphi.ingestion.doc_chunker import chunk_doc_file
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
        task["total"] = len(files)
        logger.info("Collected %d doc files from %s", len(files), path)

        all_chunks: list[Chunk] = []
        for i, fpath in enumerate(files):
            try:
                rel_path = fpath.relative_to(root)
                chunks = chunk_doc_file(fpath)
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

        # Recreate collection (idempotent re-import)
        await vector_store.recreate_collection(project)

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
        logger.error("Doc import failed: %s", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
