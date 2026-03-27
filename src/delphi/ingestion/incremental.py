"""增量更新辅助：基于文件 hash 判断变更"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from delphi.core.clients import VectorStore

logger = logging.getLogger(__name__)


def compute_file_hash(path: Path) -> str:
    """计算文件内容的 SHA256 哈希值。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def get_existing_hashes(vector_store: VectorStore, collection: str) -> dict[str, set[str]]:
    """获取 collection 中已有的 {file_path: {file_hash}} 映射。

    通过 scroll 遍历所有 points 的 payload。
    """
    file_hashes: dict[str, set[str]] = {}

    if not await vector_store.collection_exists(collection):
        return file_hashes

    offset = None
    while True:
        results, next_offset = await vector_store._client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            payload = point.payload or {}
            fp = payload.get("file_path", "")
            fh = payload.get("file_hash", "")
            if fp:
                file_hashes.setdefault(fp, set()).add(fh)
        if next_offset is None:
            break
        offset = next_offset

    return file_hashes


async def delete_file_chunks(vector_store: VectorStore, collection: str, file_path: str) -> None:
    """删除指定文件的所有 chunks。"""
    from qdrant_client import models

    await vector_store._client.delete(
        collection_name=collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_path",
                        match=models.MatchValue(value=file_path),
                    )
                ]
            )
        ),
    )
    logger.info("Deleted chunks for file: %s", file_path)
