from __future__ import annotations

from contextlib import contextmanager
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


class TestImportGit:
    @patch("delphi.cli.time.sleep")
    @patch("delphi.cli._client")
    def test_import_git_ok(self, mock_client_fn: MagicMock, _mock_sleep: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)

        mock_client.post.return_value = _mock_response(202, {"task_id": "t-123"})
        mock_client.get.return_value = _mock_response(200, {"status": "done", "total": 5, "processed": 5})

        result = runner.invoke(app, ["import", "git", "https://github.com/x/y"])
        assert result.exit_code == 0
        assert "t-123" in result.output
        mock_client.post.assert_called_once()

    @patch("delphi.cli.time.sleep")
    @patch("delphi.cli._client")
    def test_import_git_error_status(self, mock_client_fn: MagicMock, _mock_sleep: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)

        mock_client.post.return_value = _mock_response(202, {"task_id": "t-err"})
        mock_client.get.return_value = _mock_response(
            200, {"status": "failed", "error": "clone failed", "total": 0, "processed": 0}
        )

        result = runner.invoke(app, ["import", "git", "https://github.com/x/y"])
        assert result.exit_code == 1


class TestImportDocs:
    @patch("delphi.cli.time.sleep")
    @patch("delphi.cli._client")
    def test_import_docs_ok(self, mock_client_fn: MagicMock, _mock_sleep: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)

        mock_client.post.return_value = _mock_response(202, {"task_id": "t-doc"})
        mock_client.get.return_value = _mock_response(200, {"status": "done", "total": 3, "processed": 3})

        result = runner.invoke(app, ["import", "docs", "/tmp/docs"])
        assert result.exit_code == 0
        assert "t-doc" in result.output


class TestQueryStream:
    @patch("delphi.cli._client")
    def test_query_stream(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)

        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 200
        mock_stream_resp.iter_lines.return_value = [
            "data: Hello",
            "data:  World",
        ]

        @contextmanager
        def _fake_stream(*args, **kwargs):
            yield mock_stream_resp

        mock_client.stream = _fake_stream

        result = runner.invoke(app, ["query", "test question", "--stream"])
        assert result.exit_code == 0
        assert "Hello" in result.output
        assert "World" in result.output

    @patch("delphi.cli._client")
    def test_query_stream_http_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)

        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 500
        mock_stream_resp.text = "Internal Server Error"
        mock_stream_resp.json.side_effect = Exception("not json")

        @contextmanager
        def _fake_stream(*args, **kwargs):
            yield mock_stream_resp

        mock_client.stream = _fake_stream

        result = runner.invoke(app, ["query", "test question", "--stream"])
        assert result.exit_code == 1


class TestHttpError:
    @patch("delphi.cli._client")
    def test_status_http_500(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _mock_response(500, {"detail": "server error"})
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1

    @patch("delphi.cli._client")
    def test_projects_list_http_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = _mock_response(403, {"detail": "forbidden"})
        result = runner.invoke(app, ["projects", "list"])
        assert result.exit_code == 1

    @patch("delphi.cli._client")
    def test_projects_create_http_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(409, {"detail": "conflict"})
        result = runner.invoke(app, ["projects", "create", "dup"])
        assert result.exit_code == 1

    @patch("delphi.cli._client")
    def test_projects_delete_http_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.delete.return_value = _mock_response(404, {"detail": "not found"})
        result = runner.invoke(app, ["projects", "delete", "nope", "--yes"])
        assert result.exit_code == 1

    @patch("delphi.cli._client")
    def test_query_http_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(500, {"detail": "error"})
        result = runner.invoke(app, ["query", "test"])
        assert result.exit_code == 1

    @patch("delphi.cli._client")
    def test_handle_http_error_no_json(self, mock_client_fn: MagicMock) -> None:
        """_handle_http_error falls back to resp.text when json() raises."""
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 502
        resp.json.side_effect = Exception("not json")
        resp.text = "Bad Gateway"
        mock_client.get.return_value = resp
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1


class TestProjectsDeleteConfirm:
    @patch("delphi.cli._client")
    def test_projects_delete_confirm_yes(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.delete.return_value = _mock_response(204)
        result = runner.invoke(app, ["projects", "delete", "myproj"], input="y\n")
        assert result.exit_code == 0
        assert "myproj" in result.output

    @patch("delphi.cli._client")
    def test_projects_delete_confirm_no(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        result = runner.invoke(app, ["projects", "delete", "myproj"], input="n\n")
        assert result.exit_code != 0
        mock_client.delete.assert_not_called()


class TestClientAndApiUrl:
    def test_client_default_base_url(self) -> None:
        from delphi.cli import _client, _state

        original = _state["api_url"]
        try:
            _state["api_url"] = "http://localhost:9999"
            with _client() as c:
                assert str(c.base_url) == "http://localhost:9999"
        finally:
            _state["api_url"] = original

    def test_api_url_option(self) -> None:
        """--api-url global option changes the base URL used by _client."""
        from delphi.cli import _state

        original = _state["api_url"]
        try:
            with patch("delphi.cli._client") as mock_client_fn:
                mock_client = MagicMock()
                mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
                mock_client.get.return_value = _mock_response(200, {})
                runner.invoke(app, ["--api-url", "http://custom:1234", "status"])
                assert _state["api_url"] == "http://custom:1234"
        finally:
            _state["api_url"] = original


class TestImportGitHttpError:
    @patch("delphi.cli._client")
    def test_import_git_post_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(400, {"detail": "bad request"})
        result = runner.invoke(app, ["import", "git", "https://github.com/x/y"])
        assert result.exit_code == 1

    @patch("delphi.cli._client")
    def test_import_git_connection_error(self, mock_client_fn: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("refused")
        result = runner.invoke(app, ["import", "git", "https://github.com/x/y"])
        assert result.exit_code == 2

    @patch("delphi.cli.time.sleep")
    @patch("delphi.cli._client")
    def test_import_git_poll_http_error(self, mock_client_fn: MagicMock, _mock_sleep: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_fn.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(202, {"task_id": "t-poll"})
        mock_client.get.return_value = _mock_response(500, {"detail": "poll error"})
        result = runner.invoke(app, ["import", "git", "https://github.com/x/y"])
        assert result.exit_code == 1
