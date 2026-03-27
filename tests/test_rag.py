from __future__ import annotations

import contextlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.retrieval.rag import ScoredChunk, build_prompt

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
    embedding.embed = AsyncMock(return_value=[[0.1] * 1024])
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
