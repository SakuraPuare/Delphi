"""集成测试：API 端点请求/响应。

使用 FastAPI TestClient + mock 后端服务。
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.core.clients import EmbeddingResult, SparseVector
from delphi.retrieval.rag import ScoredChunk
from delphi.retrieval.session import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse_events(text: str) -> list[dict]:
    """解析 SSE 文本为事件列表。"""
    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


async def _async_gen_tokens(tokens: list[str]):
    """创建异步 token 生成器。"""
    for t in tokens:
        yield t

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_app_state():
    embedding = AsyncMock()
    fake_sparse = SparseVector(indices=[0, 1, 2], values=[0.1, 0.2, 0.3])
    embedding.embed_all = AsyncMock(
        return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[fake_sparse])
    )
    embedding.close = AsyncMock()

    vector_store = AsyncMock()
    vector_store.ensure_collection = AsyncMock()
    vector_store.collection_exists = AsyncMock(return_value=True)
    vector_store.count = AsyncMock(return_value=42)
    vector_store.search = AsyncMock(return_value=[])
    vector_store.close = AsyncMock()
    vector_store.delete_collection = AsyncMock()

    model_manager = MagicMock()
    model_manager.list_models.return_value = []
    model_manager.get_vllm_models = AsyncMock(return_value=[])

    graph_store = MagicMock()
    graph_store.get.return_value = None

    return embedding, vector_store, model_manager, graph_store


@pytest.fixture()
def client():
    embedding, vector_store, model_manager, graph_store = _mock_app_state()

    @asynccontextmanager
    async def _test_lifespan(a):
        a.state.embedding = embedding
        a.state.vector_store = vector_store
        a.state.reranker = None
        a.state.sessions = SessionStore()
        a.state.model_manager = model_manager
        a.state.graph_store = graph_store
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, vector_store, embedding
    app.router.lifespan_context = original


def _make_scored_point(text, file_path, score):
    pt = MagicMock()
    pt.payload = {"text": text, "file_path": file_path, "start_line": 1, "end_line": 10}
    pt.score = score
    return pt


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    def test_health_returns_ok(self, client):
        c, _, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_status_returns_service_info(self, client):
        c, _, _ = client
        resp = c.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "vllm" in data
        assert "qdrant" in data
        assert "embedding" in data


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class TestProjectEndpoints:
    def test_create_project(self, client):
        c, mock_vs, _ = client
        resp = c.post("/projects", json={"name": "test-proj", "description": "A test"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-proj"
        assert data["description"] == "A test"
        mock_vs.ensure_collection.assert_awaited_once_with("test-proj")

    def test_list_projects(self, client):
        c, mock_vs, _ = client
        col = MagicMock()
        col.name = "proj-a"
        collections_resp = MagicMock()
        collections_resp.collections = [col]
        mock_vs._client = AsyncMock()
        mock_vs._client.get_collections = AsyncMock(return_value=collections_resp)

        resp = c.get("/projects")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "proj-a" in names

    def test_delete_project(self, client):
        c, mock_vs, _ = client
        resp = c.delete("/projects/test-proj")
        assert resp.status_code == 204
        mock_vs.delete_collection.assert_awaited_once_with("test-proj")


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class TestImportEndpoints:
    @patch("delphi.api.routes.import_.run_git_import", new_callable=AsyncMock)
    @patch("delphi.api.routes.import_.create_task", return_value="task-001")
    def test_import_git_returns_202(self, _create, _run, client):
        c, _, _ = client
        resp = c.post("/import/git", json={"url": "https://github.com/x/y", "project": "proj"})
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "task-001"
        assert data["status"] == "pending"

    @patch("delphi.api.routes.import_.run_doc_import", new_callable=AsyncMock)
    @patch("delphi.api.routes.import_.create_task", return_value="task-002")
    def test_import_docs_returns_202(self, _create, _run, client):
        c, _, _ = client
        resp = c.post("/import/docs", json={"path": "/tmp/docs", "project": "proj"})
        assert resp.status_code == 202
        assert resp.json()["task_id"] == "task-002"

    @patch("delphi.api.routes.import_.run_media_import", new_callable=AsyncMock)
    @patch("delphi.api.routes.import_.create_task", return_value="task-003")
    def test_import_media_returns_202(self, _create, _run, client):
        c, _, _ = client
        resp = c.post("/import/media", json={"path": "/tmp/media", "project": "proj"})
        assert resp.status_code == 202
        assert resp.json()["task_id"] == "task-003"

    @patch("delphi.api.routes.import_.get_task")
    def test_get_task_status(self, mock_get, client):
        c, _, _ = client
        mock_get.return_value = {
            "task_id": "t1", "status": "running",
            "progress": 0.5, "total": 10, "processed": 5, "error": None,
        }
        resp = c.get("/import/tasks/t1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    @patch("delphi.api.routes.import_.get_task", return_value=None)
    def test_get_nonexistent_task_404(self, _mock, client):
        c, _, _ = client
        resp = c.get("/import/tasks/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQueryEndpoints:
    @patch("delphi.api.routes.query.generate_sync", new_callable=AsyncMock)
    @patch("delphi.api.routes.query.retrieve", new_callable=AsyncMock)
    def test_query_returns_answer(self, mock_retrieve, mock_gen, client):
        c, _, _ = client
        mock_retrieve.return_value = [
            ScoredChunk(content="def foo(): pass", file_path="foo.py", start_line=1, end_line=1, score=0.9),
        ]
        mock_gen.return_value = "foo 是一个空函数"

        resp = c.post("/query", json={"question": "foo 是什么", "project": "proj"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "foo 是一个空函数"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["file"] == "foo.py"

    @patch("delphi.api.routes.query.retrieve", new_callable=AsyncMock)
    def test_query_empty_results(self, mock_retrieve, client):
        c, _, _ = client
        mock_retrieve.return_value = []

        resp = c.post("/query", json={"question": "不存在的内容", "project": "proj"})
        assert resp.status_code == 200
        data = resp.json()
        assert "未找到" in data["answer"]
        assert data["sources"] == []

    def test_query_empty_question_400(self, client):
        c, _, _ = client
        resp = c.post("/query", json={"question": "  ", "project": "proj"})
        assert resp.status_code == 400

    @patch("delphi.api.routes.query.generate_sync", new_callable=AsyncMock)
    @patch("delphi.api.routes.query.retrieve", new_callable=AsyncMock)
    def test_query_with_session(self, mock_retrieve, mock_gen, client):
        """带 session 的查询应返回 session_id。"""
        c, _, _ = client
        mock_retrieve.return_value = [
            ScoredChunk(content="code", file_path="a.py", start_line=1, end_line=5, score=0.9),
        ]
        mock_gen.return_value = "answer"

        # 第一次查询（不传 session_id，自动创建）
        resp1 = c.post("/query", json={"question": "first", "project": "proj"})
        assert resp1.status_code == 200
        session_id = resp1.json()["session_id"]
        assert session_id is not None

        # 第二次查询（传入 session_id）
        resp2 = c.post("/query", json={"question": "second", "project": "proj", "session_id": session_id})
        assert resp2.status_code == 200
        assert resp2.json()["session_id"] == session_id


# ---------------------------------------------------------------------------
# SSE 流式响应
# ---------------------------------------------------------------------------


class TestStreamingEndpoints:
    @patch("delphi.api.routes.query.retrieve", new_callable=AsyncMock)
    def test_stream_empty_results(self, mock_retrieve, client):
        """无检索结果时流式端点应返回 error + done 事件。"""
        c, _, _ = client
        mock_retrieve.return_value = []

        resp = c.post("/query/stream", json={"question": "nothing", "project": "proj"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert "error" in types
        assert "done" in types

    @patch("delphi.api.routes.query.generate", return_value=_async_gen_tokens(["hello", " world"]))
    @patch("delphi.api.routes.query.retrieve", new_callable=AsyncMock)
    def test_stream_with_results(self, mock_retrieve, _mock_gen, client):
        """有检索结果时应返回 token + sources + done 事件。"""
        c, _, _ = client
        mock_retrieve.return_value = [
            ScoredChunk(content="code", file_path="a.py", start_line=1, end_line=5, score=0.9),
        ]

        resp = c.post("/query/stream", json={"question": "test", "project": "proj"})
        assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert "token" in types
        assert "done" in types

    def test_stream_empty_question_400(self, client):
        c, _, _ = client
        resp = c.post("/query/stream", json={"question": "", "project": "proj"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModelEndpoints:
    def test_list_models(self, client):
        c, _, _ = client
        resp = c.get("/models")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @patch("delphi.api.routes.models.ModelInfo")
    def test_register_model(self, _mock_info, client):
        c, _, _ = client
        resp = c.post("/models/register", json={
            "name": "test-model",
            "model_path": "/path/to/model",
            "model_type": "base",
        })
        # 可能 201 或 409（取决于 mock 状态）
        assert resp.status_code in (201, 409)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class TestGraphEndpoints:
    def test_get_nonexistent_graph_404(self, client):
        c, _, _ = client
        resp = c.get("/graph/nonexistent-proj")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# OpenAI 兼容
# ---------------------------------------------------------------------------


class TestOpenAICompatEndpoints:
    def test_list_models_v1(self, client):
        c, _, _ = client
        resp = c.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1  # 至少有 "delphi"
