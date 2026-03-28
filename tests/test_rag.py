from __future__ import annotations

import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.core.clients import EmbeddingResult, SparseVector
from delphi.retrieval.rag import ScoredChunk, _line_overlap_ratio, build_prompt, deduplicate_chunks

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

SAMPLE_CHUNKS = [
    ScoredChunk(
        content="def hello():\n    print('hello')",
        file_path="src/main.py",
        start_line=1,
        end_line=2,
        score=0.95,
    ),
    ScoredChunk(
        content="# Getting started\nRun `python main.py`",
        file_path="docs/readme.md",
        start_line=None,
        end_line=None,
        score=0.82,
    ),
]


def _make_mock_app_state():
    """Return mocked embedding + vector_store attached to app.state."""
    embedding = AsyncMock()
    fake_sparse = SparseVector(indices=[0, 1, 2], values=[0.1, 0.2, 0.3])
    embedding.embed_all = AsyncMock(return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[fake_sparse]))
    vector_store = AsyncMock()
    return embedding, vector_store


def _scored_points_from_chunks(chunks: list[ScoredChunk]):
    """Convert ScoredChunk list to mock ScoredPoint objects."""
    points = []
    for c in chunks:
        pt = MagicMock()
        pt.payload = {
            "content": c.content,
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
        }
        pt.score = c.score
        points.append(pt)
    return points


@pytest.fixture()
def client():
    embedding, vector_store = _make_mock_app_state()

    # Override the lifespan so it doesn't create real clients
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _test_lifespan(a):
        a.state.embedding = embedding
        a.state.vector_store = vector_store
        a.state.reranker = None
        from delphi.retrieval.session import SessionStore

        a.state.sessions = SessionStore()
        a.state.graph_store = None
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.router.lifespan_context = original_lifespan


# ---------------------------------------------------------------------------
# build_prompt tests
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_basic_structure(self):
        messages = build_prompt("what is this?", SAMPLE_CHUNKS)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_contains_question(self):
        messages = build_prompt("how to run?", SAMPLE_CHUNKS)
        assert "how to run?" in messages[1]["content"]

    def test_contains_file_paths(self):
        messages = build_prompt("q", SAMPLE_CHUNKS)
        user_msg = messages[1]["content"]
        assert "src/main.py" in user_msg
        assert "docs/readme.md" in user_msg

    def test_line_numbers_included(self):
        messages = build_prompt("q", SAMPLE_CHUNKS)
        user_msg = messages[1]["content"]
        assert "行 1-2" in user_msg

    def test_no_line_numbers_when_none(self):
        chunk = ScoredChunk(content="x", file_path="a.md", start_line=None, end_line=None, score=0.5)
        messages = build_prompt("q", [chunk])
        user_msg = messages[1]["content"]
        assert "行" not in user_msg

    def test_context_boundaries(self):
        messages = build_prompt("q", SAMPLE_CHUNKS)
        user_msg = messages[1]["content"]
        assert "---上下文开始---" in user_msg
        assert "---上下文结束---" in user_msg


# ---------------------------------------------------------------------------
# /query endpoint tests
# ---------------------------------------------------------------------------


class TestQueryEndpoint:
    def test_empty_question_returns_400(self, client):
        resp = client.post("/query", json={"question": "  ", "project": "p"})
        assert resp.status_code == 400

    def test_no_chunks_returns_no_results_message(self, client):
        app.state.vector_store.search = AsyncMock(return_value=[])
        resp = client.post("/query", json={"question": "hello", "project": "proj"})
        assert resp.status_code == 200
        data = resp.json()
        assert "未找到" in data["answer"]
        assert data["sources"] == []

    @patch("delphi.api.routes.query.generate_sync", new_callable=AsyncMock)
    def test_successful_query(self, mock_gen, client):
        mock_gen.return_value = "The answer is 42."
        points = _scored_points_from_chunks(SAMPLE_CHUNKS)
        app.state.vector_store.search = AsyncMock(return_value=points)

        resp = client.post("/query", json={"question": "what?", "project": "proj"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "The answer is 42."
        assert len(data["sources"]) == 2
        assert data["sources"][0]["file"] == "src/main.py"
        assert data["sources"][0]["start_line"] == 1


# ---------------------------------------------------------------------------
# /query/stream endpoint tests
# ---------------------------------------------------------------------------


class TestQueryStreamEndpoint:
    def test_empty_question_returns_400(self, client):
        resp = client.post("/query/stream", json={"question": "", "project": "p"})
        assert resp.status_code == 400

    def test_no_chunks_returns_error_sse(self, client):
        app.state.vector_store.search = AsyncMock(return_value=[])
        resp = client.post("/query/stream", json={"question": "hello", "project": "proj"})
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert any(e.get("type") == "error" for e in events)
        assert any(e.get("type") == "done" for e in events)

    @patch("delphi.api.routes.query.generate")
    def test_successful_stream(self, mock_gen, client):
        async def fake_generate(*_args, **_kwargs):
            for tok in ["Hello", " world"]:
                yield tok

        mock_gen.return_value = fake_generate()
        points = _scored_points_from_chunks(SAMPLE_CHUNKS)
        app.state.vector_store.search = AsyncMock(return_value=points)

        resp = client.post("/query/stream", json={"question": "hi", "project": "proj"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse(resp.text)
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) == 2
        assert token_events[0]["content"] == "Hello"

        source_events = [e for e in events if e.get("type") == "sources"]
        assert len(source_events) == 1
        assert len(source_events[0]["sources"]) == 2

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text into a list of JSON objects."""
    events = []
    for line in text.strip().splitlines():
        if line.startswith("data: "):
            with contextlib.suppress(json.JSONDecodeError):
                events.append(json.loads(line[len("data: ") :]))
    return events


# ---------------------------------------------------------------------------
# RerankerClient tests (mocked httpx)
# ---------------------------------------------------------------------------


class TestRerankerClient:
    @pytest.mark.asyncio
    async def test_rerank_returns_sorted_by_score(self):
        """rerank 返回按 score 降序排列的 (index, score) 列表。"""
        from delphi.retrieval.rag import RerankerClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"index": 0, "score": 0.3},
            {"index": 1, "score": 0.9},
            {"index": 2, "score": 0.6},
        ]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        rc = RerankerClient(base_url="http://fake:8002")
        rc._client = mock_client

        result = await rc.rerank("query", ["text0", "text1", "text2"])
        assert result == [(1, 0.9), (2, 0.6), (0, 0.3)]
        mock_client.post.assert_awaited_once()
        await rc.close()

    @pytest.mark.asyncio
    async def test_rerank_with_top_k(self):
        """rerank 传入 top_k 时截断结果。"""
        from delphi.retrieval.rag import RerankerClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"index": 0, "score": 0.3},
            {"index": 1, "score": 0.9},
            {"index": 2, "score": 0.6},
        ]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        rc = RerankerClient(base_url="http://fake:8002")
        rc._client = mock_client

        result = await rc.rerank("query", ["a", "b", "c"], top_k=2)
        assert len(result) == 2
        assert result[0][0] == 1  # highest score first
        await rc.close()

    @pytest.mark.asyncio
    async def test_rerank_calls_correct_endpoint(self):
        """rerank 调用 /rerank 端点，传入正确参数。"""
        from delphi.retrieval.rag import RerankerClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"index": 0, "score": 0.5}]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        rc = RerankerClient(base_url="http://fake:8002")
        rc._client = mock_client

        await rc.rerank("my query", ["doc1"])
        call_args = mock_client.post.call_args
        assert "/rerank" in call_args[0][0]
        body = call_args[1]["json"] if "json" in call_args[1] else call_args.kwargs["json"]
        assert body["query"] == "my query"
        assert body["texts"] == ["doc1"]
        assert body["truncate"] is True
        await rc.close()


# ---------------------------------------------------------------------------
# retrieve() with reranker tests
# ---------------------------------------------------------------------------


class TestRetrieveWithReranker:
    @pytest.mark.asyncio
    async def test_retrieve_without_reranker(self):
        """不传 reranker 时，直接返回 vector_store 结果。"""
        from delphi.retrieval.rag import retrieve

        fake_sparse = SparseVector(indices=[0], values=[1.0])
        embedding_client = AsyncMock()
        embedding_client.embed_all = AsyncMock(return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[fake_sparse]))

        points = _scored_points_from_chunks(SAMPLE_CHUNKS)
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=points)

        chunks = await retrieve(
            question="test",
            project="proj",
            top_k=5,
            embedding_client=embedding_client,
            vector_store=vector_store,
            reranker=None,
        )
        assert len(chunks) == 2
        vector_store.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retrieve_with_reranker_calls_rerank(self):
        """传入 reranker 时，先召回再 rerank。"""
        from delphi.retrieval.rag import RerankerClient, retrieve

        fake_sparse = SparseVector(indices=[0], values=[1.0])
        embedding_client = AsyncMock()
        embedding_client.embed_all = AsyncMock(return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[fake_sparse]))

        points = _scored_points_from_chunks(SAMPLE_CHUNKS)
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=points)

        reranker = AsyncMock(spec=RerankerClient)
        reranker.rerank = AsyncMock(return_value=[(1, 0.95), (0, 0.80)])

        chunks = await retrieve(
            question="test",
            project="proj",
            top_k=5,
            embedding_client=embedding_client,
            vector_store=vector_store,
            reranker=reranker,
        )
        reranker.rerank.assert_awaited_once()
        # reranker 返回 2 个结果
        assert len(chunks) == 2
        # score 应该来自 reranker
        assert chunks[0].score == 0.95
        assert chunks[1].score == 0.80

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.settings")
    async def test_retrieve_with_reranker_uses_retrieve_top_k(self, mock_settings):
        """启用 reranker 时，初始召回使用 settings.retrieve_top_k。"""
        from delphi.retrieval.rag import RerankerClient, retrieve

        mock_settings.retrieve_top_k = 20
        mock_settings.reranker_top_k = 5

        fake_sparse = SparseVector(indices=[0], values=[1.0])
        embedding_client = AsyncMock()
        embedding_client.embed_all = AsyncMock(return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[fake_sparse]))

        points = _scored_points_from_chunks(SAMPLE_CHUNKS)
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=points)

        reranker = AsyncMock(spec=RerankerClient)
        reranker.rerank = AsyncMock(return_value=[(0, 0.9)])

        await retrieve(
            question="test",
            project="proj",
            top_k=5,
            embedding_client=embedding_client,
            vector_store=vector_store,
            reranker=reranker,
        )
        # vector_store.search 应该用 retrieve_top_k=20 而不是 top_k=5
        search_call = vector_store.search.call_args
        assert search_call.kwargs.get("top_k") == 20 or search_call[1].get("top_k") == 20


# ---------------------------------------------------------------------------
# 去重测试
# ---------------------------------------------------------------------------


class TestLineOverlapRatio:
    """_line_overlap_ratio 计算测试"""

    def test_complete_overlap(self):
        assert _line_overlap_ratio(1, 10, 1, 10) == 1.0

    def test_no_overlap(self):
        assert _line_overlap_ratio(1, 5, 10, 15) == 0.0

    def test_partial_overlap(self):
        # 范围 1-10 和 6-15，重叠 6-10 = 5 行，较小范围长度 10，比例 = 5/10 = 0.5
        ratio = _line_overlap_ratio(1, 10, 6, 15)
        assert ratio == pytest.approx(0.5)

    def test_one_contains_other(self):
        # 范围 1-20 包含 5-10，重叠 5-10 = 6 行，较小范围 5-10 长度 6，比例 = 1.0
        assert _line_overlap_ratio(1, 20, 5, 10) == 1.0

    def test_adjacent_no_overlap(self):
        # 1-5 和 6-10 不重叠
        assert _line_overlap_ratio(1, 5, 6, 10) == 0.0

    def test_single_line_overlap(self):
        # 1-5 和 5-10，重叠 5-5 = 1 行，较小范围长度 5，比例 = 1/5 = 0.2
        ratio = _line_overlap_ratio(1, 5, 5, 10)
        assert ratio == pytest.approx(0.2)


class TestDeduplicateChunks:
    """deduplicate_chunks 去重测试"""

    def test_empty_list(self):
        assert deduplicate_chunks([]) == []

    def test_exact_duplicate_keeps_highest_score(self):
        chunks = [
            ScoredChunk(content="same content", file_path="a.py", start_line=1, end_line=5, score=0.7),
            ScoredChunk(content="same content", file_path="a.py", start_line=1, end_line=5, score=0.9),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_overlapping_same_file_dedup(self):
        """同文件行范围重叠 > 50% 去重，保留 score 最高的。"""
        chunks = [
            ScoredChunk(content="chunk A", file_path="a.py", start_line=1, end_line=10, score=0.9),
            ScoredChunk(content="chunk B", file_path="a.py", start_line=3, end_line=12, score=0.7),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_overlapping_different_files_no_dedup(self):
        """不同文件的重叠行范围不去重。"""
        chunks = [
            ScoredChunk(content="chunk A", file_path="a.py", start_line=1, end_line=10, score=0.9),
            ScoredChunk(content="chunk B", file_path="b.py", start_line=1, end_line=10, score=0.7),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 2

    def test_no_overlap_all_kept(self):
        chunks = [
            ScoredChunk(content="chunk A", file_path="a.py", start_line=1, end_line=5, score=0.9),
            ScoredChunk(content="chunk B", file_path="a.py", start_line=20, end_line=30, score=0.7),
            ScoredChunk(content="chunk C", file_path="b.py", start_line=1, end_line=10, score=0.5),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 3

    def test_none_lines_no_overlap_dedup(self):
        """start_line/end_line 为 None 时不做重叠去重。"""
        chunks = [
            ScoredChunk(content="chunk A", file_path="a.py", start_line=None, end_line=None, score=0.9),
            ScoredChunk(content="chunk B", file_path="a.py", start_line=None, end_line=None, score=0.7),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Query rewrite tests
# ---------------------------------------------------------------------------


class TestRewriteQuery:
    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.generate_sync")
    async def test_successful_rewrite(self, mock_gen):
        from delphi.retrieval.rag import rewrite_query

        mock_gen.return_value = "EmbeddingClient 配置方法"
        result = await rewrite_query("怎么配置那个嵌入的东西", "http://fake:8000", "model")
        assert result == "EmbeddingClient 配置方法"

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.generate_sync")
    async def test_rewrite_failure_fallback(self, mock_gen):
        from delphi.retrieval.rag import rewrite_query

        mock_gen.side_effect = Exception("LLM down")
        result = await rewrite_query("原始问题", "http://fake:8000", "model")
        assert result == "原始问题"

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.generate_sync")
    async def test_empty_rewrite_fallback(self, mock_gen):
        from delphi.retrieval.rag import rewrite_query

        mock_gen.return_value = "   "
        result = await rewrite_query("原始问题", "http://fake:8000", "model")
        assert result == "原始问题"
