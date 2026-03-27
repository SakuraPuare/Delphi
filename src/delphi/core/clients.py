from __future__ import annotations

import logging

import httpx
from qdrant_client import AsyncQdrantClient, models

from delphi.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """BGE-M3 embedding 服务客户端（兼容 HuggingFace TEI 接口）"""

    def __init__(self, base_url: str | None = None, batch_size: int = 32) -> None:
        self.base_url = (base_url or settings.embedding_url).rstrip("/")
        self.batch_size = batch_size
        self._client = httpx.AsyncClient(timeout=120.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = await self._client.post(
                f"{self.base_url}/embed",
                json={"inputs": batch},
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json())
        return all_embeddings

    async def close(self) -> None:
        await self._client.aclose()


class VectorStore:
    """Qdrant 向量存储封装"""

    VECTOR_SIZE = 1024  # BGE-M3 dense vector dimension

    def __init__(self, url: str | None = None) -> None:
        self._client = AsyncQdrantClient(url=url or settings.qdrant_url)

    async def ensure_collection(self, name: str) -> None:
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}
        if name not in existing:
            await self._client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("Created collection: %s", name)

    async def recreate_collection(self, name: str) -> None:
        """Drop and recreate collection — used for idempotent re-imports."""
        if await self.collection_exists(name):
            await self.delete_collection(name)
        await self._client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=self.VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )
        logger.info("Recreated collection: %s", name)

    async def delete_collection(self, name: str) -> None:
        await self._client.delete_collection(collection_name=name)
        logger.info("Deleted collection: %s", name)

    async def collection_exists(self, name: str) -> bool:
        collections = await self._client.get_collections()
        return name in {c.name for c in collections.collections}

    async def upsert(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict],
    ) -> None:
        points = [
            models.PointStruct(id=uid, vector=vec, payload=payload)
            for uid, vec, payload in zip(ids, vectors, payloads, strict=False)
        ]
        await self._client.upsert(collection_name=collection, points=points)

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
    ) -> list[models.ScoredPoint]:
        return await self._client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
        ).points

    async def count(self, collection: str) -> int:
        info = await self._client.get_collection(collection_name=collection)
        return info.points_count or 0

    async def close(self) -> None:
        await self._client.close()

    async def healthy(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False
