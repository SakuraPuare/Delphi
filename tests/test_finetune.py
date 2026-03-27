from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.finetune.exporter import export_alpaca, export_jsonl, export_sharegpt
from delphi.finetune.generator import generate_qa_pairs

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

SAMPLE_QA = [
    {"question": "如何初始化项目？", "answer": "使用 init 命令", "source": "docs/setup.md"},
    {"question": "如何运行测试？", "answer": "执行 pytest", "source": "docs/testing.md"},
]


def _make_scroll_points(chunks: list[dict]) -> list[MagicMock]:
    """Build mock Qdrant ScoredPoint objects from chunk dicts."""
    points = []
    for c in chunks:
        pt = MagicMock()
        pt.payload = {"text": c["text"], "file_path": c.get("file_path", "unknown")}
        points.append(pt)
    return points


async def _async_iter(items):
    """Wrap a list into an async iterator."""
    for item in items:
        yield item


def _make_mock_app_state():
    embedding = AsyncMock()
    vector_store = AsyncMock()
    return embedding, vector_store


@pytest.fixture()
def client():
    embedding, vector_store = _make_mock_app_state()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _test_lifespan(a):
        a.state.embedding = embedding
        a.state.vector_store = vector_store
        a.state.reranker = None
        from delphi.retrieval.session import SessionStore

        a.state.sessions = SessionStore()
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.router.lifespan_context = original_lifespan


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


class TestGenerateQAPairs:
    @pytest.mark.asyncio
    @patch("delphi.finetune.generator.generate_sync", new_callable=AsyncMock)
    @patch("delphi.finetune.generator.VectorStore")
    async def test_normal_generation(self, mock_vs_cls, mock_gen):
        """generate_qa_pairs yields correct QA dicts from scrolled chunks."""
        chunks = [
            {"text": "def hello():\n    print('hello')", "file_path": "src/main.py"},
            {"text": "# Setup guide\nRun install", "file_path": "docs/setup.md"},
        ]
        points = _make_scroll_points(chunks)

        mock_vs = MagicMock()
        mock_vs._client.scroll = AsyncMock(return_value=(points, None))
        mock_vs_cls.return_value = mock_vs

        # First call per chunk: questions; second call per chunk: answer
        mock_gen.side_effect = [
            "如何打印hello\n如何定义函数",  # questions for chunk 1
            "使用 print('hello')",           # answer for q1 of chunk 1
            "使用 def 关键字",               # answer for q2 of chunk 1
            "如何安装\n如何运行",            # questions for chunk 2
            "执行 install 命令",             # answer for q1 of chunk 2
            "执行 run 命令",                 # answer for q2 of chunk 2
        ]

        results = []
        async for pair in generate_qa_pairs(
            project="test_project",
            num_samples=10,
            questions_per_chunk=2,
            vector_store=mock_vs,
        ):
            results.append(pair)

        assert len(results) == 4
        assert results[0]["question"] == "如何打印hello"
        assert results[0]["answer"] == "使用 print('hello')"
        assert results[0]["source"] == "src/main.py"
        assert results[3]["source"] == "docs/setup.md"

    @pytest.mark.asyncio
    @patch("delphi.finetune.generator.generate_sync", new_callable=AsyncMock)
    @patch("delphi.finetune.generator.VectorStore")
    async def test_empty_chunks_returns_empty(self, mock_vs_cls, mock_gen):
        """When scroll returns no points, generator yields nothing."""
        mock_vs = MagicMock()
        mock_vs._client.scroll = AsyncMock(return_value=([], None))
        mock_vs_cls.return_value = mock_vs

        results = []
        async for pair in generate_qa_pairs(
            project="empty_project",
            vector_store=mock_vs,
        ):
            results.append(pair)

        assert results == []
        mock_gen.assert_not_called()


# ---------------------------------------------------------------------------
# Exporter tests
# ---------------------------------------------------------------------------


class TestExportJsonl:
    @pytest.mark.asyncio
    async def test_export_jsonl_format(self, tmp_path: Path):
        """export_jsonl writes one JSON object per line with all fields."""
        output = tmp_path / "out.jsonl"
        count = await export_jsonl(_async_iter(SAMPLE_QA), output)

        assert count == 2
        lines = output.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

        row = json.loads(lines[0])
        assert row["question"] == SAMPLE_QA[0]["question"]
        assert row["answer"] == SAMPLE_QA[0]["answer"]
        assert row["source"] == SAMPLE_QA[0]["source"]


class TestExportAlpaca:
    @pytest.mark.asyncio
    async def test_export_alpaca_format(self, tmp_path: Path):
        """export_alpaca writes Alpaca-style records with instruction/input/output."""
        output = tmp_path / "out.alpaca.jsonl"
        count = await export_alpaca(_async_iter(SAMPLE_QA), output)

        assert count == 2
        lines = output.read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(lines[0])
        assert row["instruction"] == SAMPLE_QA[0]["question"]
        assert row["input"] == ""
        assert row["output"] == SAMPLE_QA[0]["answer"]


class TestExportSharegpt:
    @pytest.mark.asyncio
    async def test_export_sharegpt_format(self, tmp_path: Path):
        """export_sharegpt writes ShareGPT conversation format."""
        output = tmp_path / "out.sharegpt.jsonl"
        count = await export_sharegpt(_async_iter(SAMPLE_QA), output)

        assert count == 2
        lines = output.read_text(encoding="utf-8").strip().splitlines()
        row = json.loads(lines[1])
        convs = row["conversations"]
        assert len(convs) == 2
        assert convs[0]["from"] == "human"
        assert convs[0]["value"] == SAMPLE_QA[1]["question"]
        assert convs[1]["from"] == "gpt"
        assert convs[1]["value"] == SAMPLE_QA[1]["answer"]


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


class TestFinetuneAPI:
    def test_post_finetune_generate_returns_task_info(self, client):
        """POST /finetune/generate returns 202 with a TaskInfo body."""
        resp = client.post(
            "/finetune/generate",
            json={
                "project": "my_project",
                "num_samples": 50,
                "questions_per_chunk": 2,
                "format": "jsonl",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"
