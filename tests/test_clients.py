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

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=32)
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

        ec = EmbeddingClient(base_url="http://fake:8001", batch_size=2)
        mock_client = AsyncMock()
        mock_client.post = fake_post
        ec._client = mock_client

        result = await ec.embed(["a", "b", "c", "d", "e"])
        assert len(result) == 5
        assert call_count == 3  # ceil(5/2) = 3 batches
        await ec.close()
