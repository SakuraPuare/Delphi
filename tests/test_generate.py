"""Tests for retrieval/rag.py generate and generate_sync."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from delphi.retrieval.rag import generate, generate_sync

MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello"},
]
VLLM_URL = "http://fake-vllm:8000"
MODEL = "test-model"


class TestGenerateSync:
    @pytest.mark.asyncio
    async def test_returns_content(self):
        fake_resp = MagicMock()
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = {"choices": [{"message": {"content": "Hi there!"}}]}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=fake_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("delphi.retrieval.rag.httpx.AsyncClient", return_value=mock_client_instance):
            result = await generate_sync(MESSAGES, VLLM_URL, MODEL)

        assert result == "Hi there!"
        mock_client_instance.post.assert_awaited_once()


class TestGenerate:
    @pytest.mark.asyncio
    async def test_yields_tokens(self):
        lines = [
            f"data: {json.dumps({'choices': [{'delta': {'content': 'Hello'}}]})}",
            f"data: {json.dumps({'choices': [{'delta': {'content': ' world'}}]})}",
            "data: [DONE]",
        ]

        async def fake_aiter_lines():
            for line in lines:
                yield line

        mock_resp = AsyncMock()
        mock_resp.aiter_lines = fake_aiter_lines
        mock_resp.raise_for_status = MagicMock()

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("delphi.retrieval.rag.httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate(MESSAGES, VLLM_URL, MODEL)]

        assert tokens == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_handles_done_marker(self):
        lines = [
            f"data: {json.dumps({'choices': [{'delta': {'content': 'A'}}]})}",
            "data: [DONE]",
            f"data: {json.dumps({'choices': [{'delta': {'content': 'B'}}]})}",
        ]

        async def fake_aiter_lines():
            for line in lines:
                yield line

        mock_resp = AsyncMock()
        mock_resp.aiter_lines = fake_aiter_lines
        mock_resp.raise_for_status = MagicMock()

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("delphi.retrieval.rag.httpx.AsyncClient", return_value=mock_client):
            tokens = [t async for t in generate(MESSAGES, VLLM_URL, MODEL)]

        # Should stop at [DONE], not yield "B"
        assert tokens == ["A"]
