from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from qdrant_client import AsyncQdrantClient, models

from delphi.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SparseVector:
    """稀疏向量，与 TEI /embed_sparse 返回格式对齐。"""

    indices: list[int]
    values: list[float]


@dataclass
class EmbeddingResult:
    """embed_all 的返回结果，包含 dense 和 sparse 向量。"""

    dense: list[list[float]]
    sparse: list[SparseVector]


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

    async def embed_sparse(self, texts: list[str]) -> list[SparseVector]:
        """调用 TEI /embed_sparse 接口获取稀疏向量。"""
        all_sparse: list[SparseVector] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = await self._client.post(
                f"{self.base_url}/embed_sparse",
                json={"inputs": batch},
            )
            resp.raise_for_status()
            for token_list in resp.json():
                indices = [t["index"] for t in token_list]
                values = [float(t["value"]) for t in token_list]
                all_sparse.append(SparseVector(indices=indices, values=values))
        return all_sparse

    async def embed_all(self, texts: list[str]) -> EmbeddingResult:
        """并发调用 /embed 和 /embed_sparse，同时返回 dense 和 sparse 向量。"""
        dense, sparse = await asyncio.gather(
            self.embed(texts),
            self.embed_sparse(texts),
        )
        return EmbeddingResult(dense=dense, sparse=sparse)

    async def close(self) -> None:
        await self._client.aclose()


class VectorStore:
    """Qdrant 向量存储封装"""

    VECTOR_SIZE = 1024  # BGE-M3 dense vector dimension

    def __init__(self, url: str | None = None, *, client: AsyncQdrantClient | None = None) -> None:
        self._client = client or AsyncQdrantClient(url=url or settings.qdrant_url)

    def _collection_config(self) -> dict:
        """返回 collection 创建所需的 vectors_config 和 sparse_vectors_config。"""
        return {
            "vectors_config": {
                "dense": models.VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            },
            "sparse_vectors_config": {
                "sparse": models.SparseVectorParams(),
            },
        }

    async def ensure_collection(self, name: str) -> None:
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}
        if name not in existing:
            await self._client.create_collection(
                collection_name=name,
                **self._collection_config(),
            )
            logger.info("Created collection: %s", name)

    async def recreate_collection(self, name: str) -> None:
        """Drop and recreate collection — used for idempotent re-imports."""
        if await self.collection_exists(name):
            await self.delete_collection(name)
        await self._client.create_collection(
            collection_name=name,
            **self._collection_config(),
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
        sparse_vectors: list[SparseVector] | None = None,
    ) -> None:
        points: list[models.PointStruct] = []
        for idx, (uid, dense_vec, payload) in enumerate(zip(ids, vectors, payloads, strict=False)):
            vector: dict = {"dense": dense_vec}
            if sparse_vectors is not None:
                sv = sparse_vectors[idx]
                vector["sparse"] = models.SparseVector(
                    indices=sv.indices,
                    values=sv.values,
                )
            points.append(models.PointStruct(id=uid, vector=vector, payload=payload))
        await self._client.upsert(collection_name=collection, points=points)

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        sparse_vector: SparseVector | None = None,
    ) -> list[models.ScoredPoint]:
        if sparse_vector is not None:
            # 混合检索：dense + sparse prefetch，RRF 融合
            result = await self._client.query_points(
                collection_name=collection,
                prefetch=[
                    models.Prefetch(query=vector, using="dense", limit=top_k * 2),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_vector.indices,
                            values=sparse_vector.values,
                        ),
                        using="sparse",
                        limit=top_k * 2,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=top_k,
            )
        else:
            # 仅 dense 检索（向后兼容）
            result = await self._client.query_points(
                collection_name=collection,
                query=vector,
                using="dense",
                limit=top_k,
            )
        return result.points

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
