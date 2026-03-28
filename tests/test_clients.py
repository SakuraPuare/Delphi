"""Tests for EmbeddingClient and VectorStore."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client import AsyncQdrantClient

from delphi.core.clients import EmbeddingClient, VectorStore

# ---------------------------------------------------------------------------
# VectorStore tests (in-memory Qdrant)
# ---------------------------------------------------------------------------


@pytest.fixture()
async def vs():
    client = AsyncQdrantClient(location=":memory:")
    store = VectorStore(client=client)
    yield store
    await client.close()


DIM = VectorStore.VECTOR_SIZE


class TestVectorStoreEnsureCollection:
    @pytest.mark.asyncio
    async def test_create_new(self, vs):
        await vs.ensure_collection("test-col")
        assert await vs.collection_exists("test-col")

    @pytest.mark.asyncio
    async def test_idempotent(self, vs):
        await vs.ensure_collection("test-col")
        await vs.ensure_collection("test-col")  # no error
        assert await vs.collection_exists("test-col")


class TestVectorStoreRecreateCollection:
    @pytest.mark.asyncio
    async def test_recreate_resets_points(self, vs):
        await vs.ensure_collection("rc")
        await vs.upsert("rc", [str(uuid.uuid4())], [[0.1] * DIM], [{"text": "hi"}])
        assert await vs.count("rc") == 1

        await vs.recreate_collection("rc")
        assert await vs.collection_exists("rc")
        assert await vs.count("rc") == 0


class TestVectorStoreUpsertAndCount:
    @pytest.mark.asyncio
    async def test_upsert_then_count(self, vs):
        await vs.ensure_collection("uc")
        ids = [str(uuid.uuid4()) for _ in range(3)]
        vecs = [[float(i)] * DIM for i in range(3)]
        payloads = [{"text": f"chunk-{i}"} for i in range(3)]
        await vs.upsert("uc", ids, vecs, payloads)
        assert await vs.count("uc") == 3


class TestVectorStoreSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, vs):
        await vs.ensure_collection("sc")
        await vs.upsert("sc", [str(uuid.uuid4())], [[1.0] * DIM], [{"text": "hello"}])
        results = await vs.search("sc", [1.0] * DIM, top_k=1)
        assert len(results) == 1
        assert results[0].payload["text"] == "hello"


class TestVectorStoreDeleteCollection:
    @pytest.mark.asyncio
    async def test_delete(self, vs):
        await vs.ensure_collection("del-me")
        assert await vs.collection_exists("del-me")
        await vs.delete_collection("del-me")
        assert not await vs.collection_exists("del-me")


class TestVectorStoreCollectionExists:
    @pytest.mark.asyncio
    async def test_true_and_false(self, vs):
        assert not await vs.collection_exists("nope")
        await vs.ensure_collection("yep")
        assert await vs.collection_exists("yep")


class TestVectorStoreHealthy:
    @pytest.mark.asyncio
    async def test_in_memory_healthy(self, vs):
        assert await vs.healthy() is True


# ---------------------------------------------------------------------------
# EmbeddingClient tests (mocked httpx)
# ---------------------------------------------------------------------------


class TestEmbeddingClientEmbed:
    @pytest.mark.asyncio
    async def test_single_batch(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [[0.1] * 10, [0.2] * 10]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=32, backend="tei")
        ec._client = mock_client

        result = await ec.embed(["hello", "world"])
        assert len(result) == 2
        mock_client.post.assert_awaited_once()
        await ec.close()

    @pytest.mark.asyncio
    async def test_multiple_batches(self):
        call_count = 0

        async def fake_post(url, json=None):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.json.return_value = [[0.1] * 10] * len(json["inputs"])
            resp.raise_for_status = MagicMock()
            return resp

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=2, backend="tei")
        mock_client = AsyncMock()
        mock_client.post = fake_post
        ec._client = mock_client

        result = await ec.embed(["a", "b", "c", "d", "e"])
        assert len(result) == 5
        assert call_count == 3  # ceil(5/2) = 3 batches
        await ec.close()


# ---------------------------------------------------------------------------
# EmbeddingClient.embed_sparse tests
# ---------------------------------------------------------------------------


class TestEmbeddingClientEmbedSparse:
    @pytest.mark.asyncio
    async def test_single_batch(self):
        """embed_sparse 单批次返回 SparseVector 列表。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            [{"index": 0, "value": 0.5}, {"index": 3, "value": 0.8}],
            [{"index": 1, "value": 0.2}],
        ]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=32, backend="tei")
        ec._client = mock_client

        result = await ec.embed_sparse(["hello", "world"])
        assert len(result) == 2
        assert result[0].indices == [0, 3]
        assert result[0].values == [0.5, 0.8]
        assert result[1].indices == [1]
        assert result[1].values == [0.2]
        mock_client.post.assert_awaited_once()
        await ec.close()

    @pytest.mark.asyncio
    async def test_multiple_batches(self):
        """embed_sparse 多批次正确拼接结果。"""
        call_count = 0

        async def fake_post(url, json=None):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.json.return_value = [[{"index": i, "value": 0.1 * (i + 1)}] for i in range(len(json["inputs"]))]
            resp.raise_for_status = MagicMock()
            return resp

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=2, backend="tei")
        mock_client = AsyncMock()
        mock_client.post = fake_post
        ec._client = mock_client

        result = await ec.embed_sparse(["a", "b", "c"])
        assert len(result) == 3
        assert call_count == 2  # ceil(3/2) = 2 batches
        # 每个 SparseVector 都有正确的结构
        for sv in result:
            assert isinstance(sv.indices, list)
            assert isinstance(sv.values, list)
        await ec.close()

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        """embed_sparse 调用 /embed_sparse 端点。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [[{"index": 0, "value": 1.0}]]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=32, backend="tei")
        ec._client = mock_client

        await ec.embed_sparse(["test"])
        call_args = mock_client.post.call_args
        assert "/embed_sparse" in call_args[0][0]
        await ec.close()


# ---------------------------------------------------------------------------
# EmbeddingClient.embed_all tests
# ---------------------------------------------------------------------------


class TestEmbeddingClientEmbedAll:
    @pytest.mark.asyncio
    async def test_returns_embedding_result(self):
        """embed_all 并发调用 embed + embed_sparse，返回 EmbeddingResult。"""
        from delphi.core.clients import EmbeddingResult, SparseVector

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=32, backend="tei")
        ec.embed = AsyncMock(return_value=[[0.1] * 10, [0.2] * 10])
        ec.embed_sparse = AsyncMock(
            return_value=[
                SparseVector(indices=[0], values=[0.5]),
                SparseVector(indices=[1], values=[0.3]),
            ]
        )

        result = await ec.embed_all(["hello", "world"])
        assert isinstance(result, EmbeddingResult)
        assert len(result.dense) == 2
        assert len(result.sparse) == 2
        assert result.dense[0] == [0.1] * 10
        assert result.sparse[0].indices == [0]
        ec.embed.assert_awaited_once_with(["hello", "world"])
        ec.embed_sparse.assert_awaited_once_with(["hello", "world"])
        await ec.close()


# ---------------------------------------------------------------------------
# VectorStore hybrid search tests (in-memory Qdrant, named vectors)
# ---------------------------------------------------------------------------


class TestVectorStoreHybridSearch:
    @pytest.fixture()
    async def store(self):
        client = AsyncQdrantClient(location=":memory:")
        store = VectorStore(client=client)
        yield store
        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_with_sparse_vectors(self, store):
        """upsert 带 sparse_vectors 不报错，count 正确。"""
        from delphi.core.clients import SparseVector

        await store.ensure_collection("hybrid")
        ids = [str(uuid.uuid4()) for _ in range(2)]
        dense_vecs = [[1.0] * DIM, [0.5] * DIM]
        payloads = [{"text": "doc-0"}, {"text": "doc-1"}]
        sparse_vecs = [
            SparseVector(indices=[0, 1, 2], values=[0.5, 0.3, 0.1]),
            SparseVector(indices=[1, 3], values=[0.8, 0.2]),
        ]
        await store.upsert("hybrid", ids, dense_vecs, payloads, sparse_vectors=sparse_vecs)
        assert await store.count("hybrid") == 2

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_results(self, store):
        """混合检索（dense + sparse）返回结果。"""
        from delphi.core.clients import SparseVector

        await store.ensure_collection("hs")
        ids = [str(uuid.uuid4()) for _ in range(3)]
        dense_vecs = [[1.0] * DIM, [0.5] * DIM, [0.0] * DIM]
        payloads = [{"text": f"chunk-{i}"} for i in range(3)]
        sparse_vecs = [
            SparseVector(indices=[0, 1], values=[1.0, 0.5]),
            SparseVector(indices=[2, 3], values=[0.8, 0.3]),
            SparseVector(indices=[0], values=[0.1]),
        ]
        await store.upsert("hs", ids, dense_vecs, payloads, sparse_vectors=sparse_vecs)

        query_sparse = SparseVector(indices=[0, 1], values=[1.0, 0.5])
        results = await store.search("hs", vector=[1.0] * DIM, sparse_vector=query_sparse, top_k=2)
        assert len(results) <= 2
        assert all(hasattr(r, "payload") for r in results)

    @pytest.mark.asyncio
    async def test_dense_only_search_backward_compat(self, store):
        """不传 sparse_vector 时走 dense-only 路径（向后兼容）。"""
        from delphi.core.clients import SparseVector

        await store.ensure_collection("dense-only")
        ids = [str(uuid.uuid4())]
        dense_vecs = [[1.0] * DIM]
        payloads = [{"text": "only-dense"}]
        sparse_vecs = [SparseVector(indices=[0], values=[1.0])]
        await store.upsert("dense-only", ids, dense_vecs, payloads, sparse_vectors=sparse_vecs)

        results = await store.search("dense-only", vector=[1.0] * DIM, top_k=1)
        assert len(results) == 1
        assert results[0].payload["text"] == "only-dense"
