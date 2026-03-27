"""集成测试共享 fixtures。

提供 mock 的向量存储、LLM、embedding 服务以及 FastAPI TestClient。
"""

from __future__ import annotations

import random
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient

from delphi.api.app import app
from delphi.core.clients import EmbeddingResult, SparseVector, VectorStore
from delphi.retrieval.session import SessionStore

VECTOR_DIM = VectorStore.VECTOR_SIZE


# ---------------------------------------------------------------------------
# Fake embedding client (deterministic, hash-based)
# ---------------------------------------------------------------------------


class FakeEmbedding:
    """确定性 fake embedding：相同文本 → 相同向量。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for t in texts:
            rng = random.Random(hash(t))
            result.append([rng.gauss(0, 1) for _ in range(VECTOR_DIM)])
        return result

    async def embed_sparse(self, texts: list[str]) -> list[SparseVector]:
        result = []
        for t in texts:
            rng = random.Random(hash(t) ^ 0xDEAD)
            indices = sorted(rng.sample(range(30522), 10))
            values = [rng.random() for _ in range(10)]
            result.append(SparseVector(indices=indices, values=values))
        return result

    async def embed_all(self, texts: list[str]) -> EmbeddingResult:
        dense = await self.embed(texts)
        sparse = await self.embed_sparse(texts)
        return EmbeddingResult(dense=dense, sparse=sparse)

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def vector_store():
    """内存 Qdrant 向量存储。"""
    client = AsyncQdrantClient(location=":memory:")
    vs = VectorStore(client=client)
    yield vs
    await vs.close()


@pytest.fixture
def fake_embedding():
    return FakeEmbedding()


@pytest.fixture
def session_store():
    return SessionStore()


@pytest.fixture
def mock_reranker():
    """Mock reranker：按原始顺序返回前 N 个结果。"""
    reranker = AsyncMock()

    async def _rerank(query: str, texts: list[str], top_k: int | None = None):
        n = top_k or len(texts)
        return [(i, 1.0 - i * 0.1) for i in range(min(n, len(texts)))]

    reranker.rerank = _rerank
    reranker.close = AsyncMock()
    return reranker


def _make_scored_point(payload: dict, score: float = 0.9):
    """创建 mock ScoredPoint。"""
    pt = MagicMock()
    pt.payload = payload
    pt.score = score
    return pt


@pytest.fixture()
def test_client(fake_embedding, session_store):
    """带 mock lifespan 的 FastAPI TestClient。"""
    mock_vs = AsyncMock()
    mock_vs.ensure_collection = AsyncMock()
    mock_vs.collection_exists = AsyncMock(return_value=True)
    mock_vs.count = AsyncMock(return_value=0)
    mock_vs.search = AsyncMock(return_value=[])
    mock_vs.close = AsyncMock()

    @asynccontextmanager
    async def _test_lifespan(a):
        a.state.embedding = fake_embedding
        a.state.vector_store = mock_vs
        a.state.reranker = None
        a.state.sessions = session_store
        a.state.model_manager = MagicMock()
        a.state.graph_store = MagicMock()
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_vs, fake_embedding
    app.router.lifespan_context = original
