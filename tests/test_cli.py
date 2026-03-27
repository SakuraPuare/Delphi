from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
from typer.testing import CliRunner

from delphi.cli import app

runner = CliRunner()


def _mock_response(status_code: int = 200, json_data: dict | list | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = ""
    return resp


class TestStatus:
    @patch("delphi.cli._client")
    def test_status_ok(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _mock_response(
            200,
            {
                "vllm": {"ok": True, "model": "Qwen2.5-7B"},
                "qdrant": {"ok": True, "collections": 3},
                "embedding": {"ok": False, "error": "unreachable"},
            },
        )
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "vllm" in result.output
        assert "qdrant" in result.output
        assert "embedding" in result.output

    @patch("delphi.cli._client")
    def test_status_connection_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("refused")
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 2


class TestProjectsList:
    @patch("delphi.cli._client")
    def test_projects_list_ok(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _mock_response(
            200,
            [
                {"name": "proj1", "chunk_count": 100, "created_at": "2024-01-01"},
                {"name": "proj2", "chunk_count": 200, "created_at": "2024-02-01"},
            ],
        )
        result = runner.invoke(app, ["projects", "list"])
        assert result.exit_code == 0
        assert "proj1" in result.output
        assert "proj2" in result.output

    @patch("delphi.cli._client")
    def test_projects_list_empty(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _mock_response(200, [])
        result = runner.invoke(app, ["projects", "list"])
        assert result.exit_code == 0
        assert "暂无项目" in result.output


class TestProjectsCreate:
    @patch("delphi.cli._client")
    def test_projects_create_ok(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(201, {"name": "myproj", "description": "", "chunk_count": 0})
        result = runner.invoke(app, ["projects", "create", "myproj"])
        assert result.exit_code == 0
        assert "myproj" in result.output
        mock_client.post.assert_called_once_with("/projects", json={"name": "myproj", "description": ""})


class TestQuery:
    @patch("delphi.cli._client")
    def test_query_non_streaming(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(
            200,
            {
                "answer": "vLLM 并发数通过 --max-num-seqs 控制",
                "sources": [
                    {"file": "docs/vllm.md", "chunk": "", "score": 0.92},
                ],
            },
        )
        result = runner.invoke(app, ["query", "如何配置并发数", "--show-sources"])
        assert result.exit_code == 0
        assert "vLLM" in result.output
        assert "docs/vllm.md" in result.output
        assert "0.92" in result.output

    @patch("delphi.cli._client")
    def test_query_no_sources(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(200, {"answer": "答案内容", "sources": []})
        result = runner.invoke(app, ["query", "测试问题"])
        assert result.exit_code == 0
        assert "答案内容" in result.output
        assert "来源" not in result.output


class TestProjectsDelete:
    @patch("delphi.cli._client")
    def test_projects_delete_with_yes(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.delete.return_value = _mock_response(204)
        result = runner.invoke(app, ["projects", "delete", "myproj", "--yes"])
        assert result.exit_code == 0
        assert "myproj" in result.output
        mock_client.delete.assert_called_once_with("/projects/myproj")
