"""Tests for model manager and model API routes."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.models.manager import ModelInfo, ModelManager

# ---------------------------------------------------------------------------
# ModelManager unit tests
# ---------------------------------------------------------------------------


class TestModelManagerRegister:
    def test_register_adds_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        info = ModelInfo(name="qwen7b", model_path="Qwen/Qwen2.5-7B")
        mgr.register(info)

        assert mgr.get("qwen7b") is not None
        assert mgr.get("qwen7b").model_path == "Qwen/Qwen2.5-7B"

    def test_register_overwrites_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        mgr.register(ModelInfo(name="m1", model_path="/old"))
        mgr.register(ModelInfo(name="m1", model_path="/new"))

        assert mgr.get("m1").model_path == "/new"
        assert len(mgr.list_models()) == 1


class TestModelManagerUnregister:
    def test_unregister_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        mgr.register(ModelInfo(name="m1", model_path="/p"))

        assert mgr.unregister("m1") is True
        assert mgr.get("m1") is None

    def test_unregister_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        assert mgr.unregister("ghost") is False


class TestModelManagerListModels:
    def test_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        assert mgr.list_models() == []

    def test_list_multiple(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        mgr.register(ModelInfo(name="a", model_path="/a"))
        mgr.register(ModelInfo(name="b", model_path="/b"))

        models = mgr.list_models()
        assert len(models) == 2
        names = {m.name for m in models}
        assert names == {"a", "b"}


class TestModelManagerActivate:
    async def test_activate_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        mgr.register(ModelInfo(name="m1", model_path="/m1"))
        mgr.register(ModelInfo(name="m2", model_path="/m2"))

        result = await mgr.activate("m1")
        assert result is True
        assert mgr.get("m1").active is True
        assert mgr.get("m2").active is False

    async def test_activate_switches_active(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        mgr.register(ModelInfo(name="m1", model_path="/m1"))
        mgr.register(ModelInfo(name="m2", model_path="/m2"))

        await mgr.activate("m1")
        await mgr.activate("m2")
        assert mgr.get("m1").active is False
        assert mgr.get("m2").active is True

    async def test_activate_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        result = await mgr.activate("ghost")
        assert result is False


class TestModelManagerPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        registry_file = tmp_path / "models" / "registry.json"
        mgr = ModelManager()
        mgr.register(ModelInfo(name="m1", model_path="/m1", description="test model"))
        mgr.register(ModelInfo(name="m2", model_path="/m2", model_type="lora", base_model="m1"))

        # Verify file was written
        assert registry_file.exists()
        data = json.loads(registry_file.read_text())
        assert len(data) == 2

        # Load into a new manager instance
        mgr2 = ModelManager()
        assert len(mgr2.list_models()) == 2
        assert mgr2.get("m1").description == "test model"
        assert mgr2.get("m2").model_type == "lora"
        assert mgr2.get("m2").base_model == "m1"

    def test_load_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()
        assert mgr.list_models() == []


class TestGetVllmModels:
    async def test_get_vllm_models_success(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"id": "Qwen2.5-7B"}, {"id": "Llama-3-8B"}]}
        mock_resp.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp

        with patch("delphi.models.manager.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_cls.return_value.__aexit__.return_value = False
            result = await mgr.get_vllm_models()

        assert result == ["Qwen2.5-7B", "Llama-3-8B"]

    async def test_get_vllm_models_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))
        mgr = ModelManager()

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("connection refused")

        with patch("delphi.models.manager.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_client
            mock_cls.return_value.__aexit__.return_value = False
            result = await mgr.get_vllm_models()

        assert result == []


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def model_client(tmp_path, monkeypatch):
    """Create a test client with a mocked ModelManager using tmp_path."""
    monkeypatch.setattr("delphi.core.config.settings.data_dir", str(tmp_path))

    @asynccontextmanager
    async def _test_lifespan(a):
        mgr = ModelManager()
        a.state.model_manager = mgr
        a.state.vector_store = AsyncMock()
        a.state.embedding = AsyncMock()
        a.state.reranker = None
        a.state.sessions = AsyncMock()
        a.state.graph_store = AsyncMock()
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.router.lifespan_context = original


class TestListModelsRoute:
    def test_list_empty(self, model_client):
        with patch.object(ModelManager, "get_vllm_models", new_callable=AsyncMock, return_value=[]):
            resp = model_client.get("/models")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_registered_and_vllm(self, model_client):
        # Register a model first
        model_client.post(
            "/models/register",
            json={"name": "my-qwen", "model_path": "Qwen/Qwen2.5-7B"},
        )
        # Mock vLLM returning an extra unregistered model
        with patch.object(
            ModelManager, "get_vllm_models", new_callable=AsyncMock, return_value=["Qwen/Qwen2.5-7B", "Llama-3-8B"]
        ):
            resp = model_client.get("/models")
        assert resp.status_code == 200
        data = resp.json()
        names = [m["name"] for m in data]
        assert "my-qwen" in names
        assert "Llama-3-8B" in names  # unregistered vLLM model also listed


class TestRegisterModelRoute:
    def test_register_success(self, model_client):
        resp = model_client.post(
            "/models/register",
            json={
                "name": "test-model",
                "model_path": "/models/test",
                "model_type": "base",
                "description": "A test model",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-model"
        assert data["model_path"] == "/models/test"
        assert data["description"] == "A test model"
        assert data["active"] is False

    def test_register_duplicate_returns_409(self, model_client):
        payload = {"name": "dup", "model_path": "/models/dup"}
        model_client.post("/models/register", json=payload)
        resp = model_client.post("/models/register", json=payload)
        assert resp.status_code == 409

    def test_register_lora_model(self, model_client):
        resp = model_client.post(
            "/models/register",
            json={
                "name": "my-lora",
                "model_path": "/adapters/lora1",
                "model_type": "lora",
                "base_model": "Qwen/Qwen2.5-7B",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_type"] == "lora"
        assert data["base_model"] == "Qwen/Qwen2.5-7B"


class TestActivateModelRoute:
    def test_activate_success(self, model_client):
        model_client.post(
            "/models/register",
            json={"name": "m1", "model_path": "/m1"},
        )
        resp = model_client.post("/models/activate", json={"name": "m1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "m1"
        assert data["active"] is True

    def test_activate_nonexistent_returns_404(self, model_client):
        resp = model_client.post("/models/activate", json={"name": "ghost"})
        assert resp.status_code == 404


class TestDeleteModelRoute:
    def test_delete_existing(self, model_client):
        model_client.post(
            "/models/register",
            json={"name": "to-delete", "model_path": "/del"},
        )
        resp = model_client.delete("/models/to-delete")
        assert resp.status_code == 204

        # Verify it's gone
        with patch.object(ModelManager, "get_vllm_models", new_callable=AsyncMock, return_value=[]):
            resp = model_client.get("/models")
        names = [m["name"] for m in resp.json()]
        assert "to-delete" not in names

    def test_delete_nonexistent_returns_404(self, model_client):
        resp = model_client.delete("/models/ghost")
        assert resp.status_code == 404
