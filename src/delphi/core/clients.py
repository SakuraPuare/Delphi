from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from loguru import logger
from qdrant_client import AsyncQdrantClient, models

from delphi.core.config import settings
from delphi.core.telemetry import get_tracer

_tracer = get_tracer(__name__)


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
    """Embedding 服务客户端（兼容 TEI / Ollama / OpenAI 兼容 / Cloudflare Workers AI）"""

    def __init__(self, base_url: str | None = None, batch_size: int = 32, backend: str | None = None) -> None:
        self.base_url = (base_url or settings.embedding_url).rstrip("/")
        self.batch_size = batch_size
        self.backend = backend or settings.embedding_backend
        self._api_key = settings.embedding_api_key
        self._client = httpx.AsyncClient(timeout=120.0)
        logger.info(
            "EmbeddingClient 初始化完成, backend={}, url={}, batch_size={}",
            self.backend,
            self.base_url,
            self.batch_size,
        )

    async def _embed_tei(self, texts: list[str]) -> list[list[float]]:
        logger.debug("TEI embed 开始, 文本数={}", len(texts))
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            logger.debug(
                "TEI embed 批次 {}/{}, 本批数量={}",
                i // self.batch_size + 1,
                -(-len(texts) // self.batch_size),
                len(batch),
            )
            resp = await self._client.post(
                f"{self.base_url}/embed",
                json={"inputs": batch},
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json())
        logger.debug("TEI embed 完成, 共获得 {} 条向量", len(all_embeddings))
        return all_embeddings

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        logger.debug("Ollama embed 开始, 文本数={}, model={}", len(texts), settings.embedding_model)
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            logger.debug(
                "Ollama embed 批次 {}/{}, 本批数量={}",
                i // self.batch_size + 1,
                -(-len(texts) // self.batch_size),
                len(batch),
            )
            resp = await self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": settings.embedding_model, "input": batch},
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json()["embeddings"])
        logger.debug("Ollama embed 完成, 共获得 {} 条向量", len(all_embeddings))
        return all_embeddings

    def _auth_headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """OpenAI 兼容接口（DeepSeek / Together / Fireworks 等）"""
        logger.debug("OpenAI 兼容 embed 开始, 文本数={}, model={}", len(texts), settings.embedding_model)
        headers = self._auth_headers()
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            logger.debug(
                "OpenAI embed 批次 {}/{}, 本批数量={}",
                i // self.batch_size + 1,
                -(-len(texts) // self.batch_size),
                len(batch),
            )
            resp = await self._client.post(
                f"{self.base_url}/v1/embeddings",
                json={"model": settings.embedding_model, "input": batch},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            all_embeddings.extend(item["embedding"] for item in data)
        logger.debug("OpenAI 兼容 embed 完成, 共获得 {} 条向量", len(all_embeddings))
        return all_embeddings

    async def _embed_cloudflare(self, texts: list[str]) -> list[list[float]]:
        """Cloudflare Workers AI 接口"""
        logger.debug("Cloudflare embed 开始, 文本数={}", len(texts))
        headers = self._auth_headers()
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            logger.debug(
                "Cloudflare embed 批次 {}/{}, 本批数量={}",
                i // self.batch_size + 1,
                -(-len(texts) // self.batch_size),
                len(batch),
            )
            resp = await self._client.post(
                self.base_url,
                json={"text": batch},
                headers=headers,
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json()["result"]["data"])
        logger.debug("Cloudflare embed 完成, 共获得 {} 条向量", len(all_embeddings))
        return all_embeddings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        logger.info("开始 embed 调用, backend={}, 文本数={}", self.backend, len(texts))
        with _tracer.start_as_current_span("embedding.embed") as span:
            span.set_attribute("embedding.backend", self.backend)
            span.set_attribute("embedding.num_texts", len(texts))
            match self.backend:
                case "ollama":
                    return await self._embed_ollama(texts)
                case "openai":
                    return await self._embed_openai(texts)
                case "cloudflare":
                    return await self._embed_cloudflare(texts)
                case _:
                    return await self._embed_tei(texts)

    async def embed_sparse(self, texts: list[str]) -> list[SparseVector]:
        """调用 TEI /embed_sparse 接口获取稀疏向量。仅 TEI 后端支持。"""
        if self.backend != "tei":
            logger.debug("当前 backend={} 不支持稀疏向量, 跳过 embed_sparse", self.backend)
            return []
        logger.debug("TEI embed_sparse 开始, 文本数={}", len(texts))
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
        logger.debug("TEI embed_sparse 完成, 共获得 {} 条稀疏向量", len(all_sparse))
        return all_sparse

    async def embed_all(self, texts: list[str]) -> EmbeddingResult:
        """并发调用 /embed 和 /embed_sparse，同时返回 dense 和 sparse 向量。"""
        logger.info("embed_all 开始, 文本数={}, backend={}", len(texts), self.backend)
        if self.backend == "ollama":
            logger.debug("Ollama 后端不支持稀疏向量, 仅获取 dense 向量")
            dense = await self.embed(texts)
            return EmbeddingResult(dense=dense, sparse=[])
        dense, sparse = await asyncio.gather(
            self.embed(texts),
            self.embed_sparse(texts),
        )
        logger.info("embed_all 完成, dense={} 条, sparse={} 条", len(dense), len(sparse))
        return EmbeddingResult(dense=dense, sparse=sparse)

    async def close(self) -> None:
        logger.debug("关闭 EmbeddingClient HTTP 连接")
        await self._client.aclose()


class VectorStore:
    """Qdrant 向量存储封装"""

    VECTOR_SIZE = 1024  # Qwen3-Embedding-0.6B / BGE-M3 默认 1024 维

    def __init__(self, url: str | None = None, *, client: AsyncQdrantClient | None = None) -> None:
        self._url = url or settings.qdrant_url
        self._client = client or AsyncQdrantClient(url=self._url)
        logger.info("VectorStore 初始化完成, url={}", self._url)

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
        logger.debug("检查 collection 是否存在: {}", name)
        collections = await self._client.get_collections()
        existing = {c.name for c in collections.collections}
        if name not in existing:
            await self._client.create_collection(
                collection_name=name,
                **self._collection_config(),
            )
            logger.info("创建 collection 成功: {}", name)
        else:
            logger.debug("collection 已存在, 跳过创建: {}", name)

    async def recreate_collection(self, name: str) -> None:
        """Drop and recreate collection — used for idempotent re-imports."""
        logger.info("重建 collection: {}", name)
        if await self.collection_exists(name):
            await self.delete_collection(name)
            logger.debug("已删除旧 collection: {}", name)
        await self._client.create_collection(
            collection_name=name,
            **self._collection_config(),
        )
        logger.info("重建 collection 完成: {}", name)

    async def delete_collection(self, name: str) -> None:
        await self._client.delete_collection(collection_name=name)
        logger.info("删除 collection: {}", name)

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
        logger.debug(
            "upsert 开始, collection={}, 点数={}, 含稀疏向量={}", collection, len(ids), sparse_vectors is not None
        )
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
        logger.info("upsert 完成, collection={}, 写入 {} 个点", collection, len(points))

    async def search(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        sparse_vector: SparseVector | None = None,
    ) -> list[models.ScoredPoint]:
        logger.info("向量检索开始, collection={}, top_k={}, hybrid={}", collection, top_k, sparse_vector is not None)
        with _tracer.start_as_current_span("vectorstore.search") as span:
            span.set_attribute("vectorstore.collection", collection)
            span.set_attribute("vectorstore.top_k", top_k)
            span.set_attribute("vectorstore.hybrid", sparse_vector is not None)
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
            span.set_attribute("vectorstore.num_results", len(result.points))
            logger.info("向量检索完成, 返回 {} 条结果", len(result.points))
            return result.points

    async def count(self, collection: str) -> int:
        info = await self._client.get_collection(collection_name=collection)
        cnt = info.points_count or 0
        logger.debug("collection={} 当前点数={}", collection, cnt)
        return cnt

    async def scroll(
        self,
        collection: str,
        limit: int = 50,
        offset: str | int | None = None,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[models.Record], str | int | None]:
        """Scroll through collection points. Returns (records, next_offset)."""
        logger.debug("scroll 开始, collection={}, limit={}, offset={}, filters={}", collection, limit, offset, filters)
        filter_conditions = None
        if filters:
            must = []
            for key, value in filters.items():
                must.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )
            filter_conditions = models.Filter(must=must)

        records, next_offset = await self._client.scroll(
            collection_name=collection,
            limit=limit,
            offset=offset,
            scroll_filter=filter_conditions,
            with_payload=True,
            with_vectors=False,
        )
        logger.debug("scroll 完成, 返回 {} 条记录, next_offset={}", len(records), next_offset)
        return records, next_offset

    async def scroll_by_file(
        self,
        collection: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        limit: int = 50,
    ) -> list[models.Record]:
        """Scroll points filtered by file_path and optional line range overlap."""
        logger.debug(
            "scroll_by_file 开始, collection={}, file_path={}, lines=[{}, {}]",
            collection,
            file_path,
            start_line,
            end_line,
        )
        must = [
            models.FieldCondition(
                key="file_path",
                match=models.MatchValue(value=file_path),
            )
        ]
        if start_line is not None and end_line is not None:
            # Keep chunks whose range overlaps [start_line, end_line]:
            #   chunk.start_line <= end_line AND chunk.end_line >= start_line
            must.append(
                models.FieldCondition(
                    key="start_line",
                    range=models.Range(lte=end_line),
                )
            )
            must.append(
                models.FieldCondition(
                    key="end_line",
                    range=models.Range(gte=start_line),
                )
            )
        records, _ = await self._client.scroll(
            collection_name=collection,
            limit=limit,
            scroll_filter=models.Filter(must=must),
            with_payload=True,
            with_vectors=False,
        )
        logger.debug("scroll_by_file 完成, 返回 {} 条记录", len(records))
        return records

    async def close(self) -> None:
        logger.debug("关闭 VectorStore 连接")
        await self._client.close()

    async def healthy(self) -> bool:
        try:
            await self._client.get_collections()
            logger.debug("VectorStore 健康检查通过")
            return True
        except Exception as e:
            logger.warning("VectorStore 健康检查失败: {}", str(e))
            return False
