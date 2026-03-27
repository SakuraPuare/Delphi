"""Tests for API routes: projects and import."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    mock_vs = AsyncMock()
    mock_embedding = AsyncMock()

    @asynccontextmanager
    async def _test_lifespan(a):
        a.state.vector_store = mock_vs
        a.state.embedding = mock_embedding
        a.state.reranker = None
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_vs, mock_embedding
    app.router.lifespan_context = original


# ---------------------------------------------------------------------------
# Projects routes
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_returns_collection_names(self, client):
        c, mock_vs, _ = client
        col1 = MagicMock()
        col1.name = "project-a"
        col2 = MagicMock()
        col2.name = "project-b"
        collections_resp = MagicMock()
        collections_resp.collections = [col1, col2]
        mock_vs._client.get_collections = AsyncMock(return_value=collections_resp)

        resp = c.get("/projects")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert names == ["project-a", "project-b"]

    def test_returns_empty_on_error(self, client):
        c, mock_vs, _ = client
        mock_vs._client.get_collections = AsyncMock(side_effect=Exception("down"))

        resp = c.get("/projects")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateProject:
    def test_create_returns_201(self, client):
        c, mock_vs, _ = client
        mock_vs.ensure_collection = AsyncMock()

        resp = c.post("/projects", json={"name": "my-proj", "description": "desc"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my-proj"
        assert data["description"] == "desc"
        mock_vs.ensure_collection.assert_awaited_once_with("my-proj")

    def test_create_idempotent(self, client):
        c, mock_vs, _ = client
        mock_vs.ensure_collection = AsyncMock()

        resp1 = c.post("/projects", json={"name": "dup"})
        resp2 = c.post("/projects", json={"name": "dup"})
        assert resp1.status_code == 201
        assert resp2.status_code == 201


class TestDeleteProject:
    def test_delete_existing_returns_204(self, client):
        c, mock_vs, _ = client
        mock_vs.collection_exists = AsyncMock(return_value=True)
        mock_vs.delete_collection = AsyncMock()

        resp = c.delete("/projects/my-proj")
        assert resp.status_code == 204
        mock_vs.collection_exists.assert_awaited_once_with("my-proj")
        mock_vs.delete_collection.assert_awaited_once_with("my-proj")

    def test_delete_nonexistent_returns_204(self, client):
        c, mock_vs, _ = client
        mock_vs.collection_exists = AsyncMock(return_value=False)

        resp = c.delete("/projects/ghost")
        assert resp.status_code == 204
        mock_vs.delete_collection.assert_not_awaited()


# ---------------------------------------------------------------------------
# Import routes
# ---------------------------------------------------------------------------


class TestImportGit:
    @patch("delphi.api.routes.import_.run_git_import", new_callable=AsyncMock)
    @patch("delphi.api.routes.import_.create_task", return_value="abc123")
    def test_returns_202_with_task_id(self, _mock_create, _mock_run, client):
        c, _, _ = client
        resp = c.post(
            "/import/git",
            json={"url": "https://github.com/x/y.git", "project": "proj"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "abc123"
        assert data["status"] == "pending"


class TestImportDocs:
    @patch("delphi.api.routes.import_.run_doc_import", new_callable=AsyncMock)
    @patch("delphi.api.routes.import_.create_task", return_value="def456")
    def test_returns_202_with_task_id(self, _mock_create, _mock_run, client):
        c, _, _ = client
        resp = c.post(
            "/import/docs",
            json={"path": "/tmp/docs", "project": "proj"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["task_id"] == "def456"
        assert data["status"] == "pending"


class TestGetTask:
    @patch("delphi.api.routes.import_.get_task")
    def test_existing_task(self, mock_get_task, client):
        c, _, _ = client
        mock_get_task.return_value = {
            "task_id": "t1",
            "status": "running",
            "progress": 0.5,
            "total": 10,
            "processed": 5,
            "error": None,
        }
        resp = c.get("/import/tasks/t1")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "t1"
        assert resp.json()["status"] == "running"

    @patch("delphi.api.routes.import_.get_task", return_value=None)
    def test_nonexistent_task_returns_404(self, _mock, client):
        c, _, _ = client
        resp = c.get("/import/tasks/nonexistent")
        assert resp.status_code == 404
