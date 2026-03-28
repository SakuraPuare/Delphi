"""增量更新辅助：基于文件 hash 判断变更"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from delphi.core.clients import VectorStore

from loguru import logger


def compute_file_hash(path: Path) -> str:
    """计算文件内容的 SHA256 哈希值。"""
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    logger.debug("计算文件哈希, file={}, hash={}", path, h[:12])
    return h


async def get_existing_hashes(vector_store: VectorStore, collection: str) -> dict[str, set[str]]:
    """获取 collection 中已有的 {file_path: {file_hash}} 映射。

    通过 scroll 遍历所有 points 的 payload。
    """
    file_hashes: dict[str, set[str]] = {}

    if not await vector_store.collection_exists(collection):
        logger.debug("集合不存在，返回空哈希映射, collection={}", collection)
        return file_hashes

    logger.debug("开始扫描已有文件哈希, collection={}", collection)
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

    logger.info("已有文件哈希扫描完成, collection={}, 文件数={}", collection, len(file_hashes))
    return file_hashes


async def delete_file_chunks(vector_store: VectorStore, collection: str, file_path: str) -> None:
    """删除指定文件的所有 chunks。"""
    logger.debug("准备删除文件分块, collection={}, file_path={}", collection, file_path)
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
    logger.info("已删除文件的全部分块, file_path={}", file_path)
