"""端到端测试：从导入项目到查询获得回答的完整流程。

使用内存 Qdrant + fake embedding + mock LLM，不需要任何外部服务。
"""

from __future__ import annotations

import json
import random
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.core.clients import EmbeddingResult, SparseVector, VectorStore
from delphi.ingestion.pipeline import create_task, get_task, run_git_import
from delphi.retrieval.rag import ScoredChunk, build_prompt, retrieve
from delphi.retrieval.session import SessionStore
from qdrant_client import AsyncQdrantClient

VECTOR_DIM = VectorStore.VECTOR_SIZE


# ---------------------------------------------------------------------------
# Fake services
# ---------------------------------------------------------------------------


class FakeEmbedding:
    """确定性 fake embedding。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[random.Random(hash(t)).gauss(0, 1) for _ in range(VECTOR_DIM)] for t in texts]

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


def _create_test_repo(tmp_path: Path) -> Path:
    """创建包含多种文件的测试仓库。"""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    (repo / "main.py").write_text(
        textwrap.dedent("""\
        class Calculator:
            def add(self, a: int, b: int) -> int:
                return a + b

            def subtract(self, a: int, b: int) -> int:
                return a - b

        def fibonacci(n: int) -> int:
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)
        """)
    )

    (repo / "utils.py").write_text(
        textwrap.dedent("""\
        def format_output(result: int) -> str:
            return f"Result: {result}"

        def validate_input(value: str) -> bool:
            return value.isdigit()
        """)
    )

    (repo / "README.md").write_text(
        textwrap.dedent("""\
        # Calculator Project

        A simple calculator with basic arithmetic operations.

        ## Usage

        ```python
        calc = Calculator()
        result = calc.add(1, 2)
        ```
        """)
    )

    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def e2e_env(tmp_path):
    """完整的 E2E 环境：内存 Qdrant + fake embedding + 测试仓库。"""
    client = AsyncQdrantClient(location=":memory:")
    vs = VectorStore(client=client)
    emb = FakeEmbedding()
    repo = _create_test_repo(tmp_path)

    yield vs, emb, repo

    await vs.close()


# ---------------------------------------------------------------------------
# E2E: Import → Search → Answer
# ---------------------------------------------------------------------------


class TestImportToQueryFlow:
    """端到端：导入项目 → 检索 → 构建 prompt → 验证回答结构。"""

    @pytest.mark.asyncio
    async def test_full_flow_import_then_query(self, e2e_env):
        """导入本地仓库后，检索应返回相关 chunks。"""
        vs, emb, repo = e2e_env

        # Step 1: 导入
        task_id = create_task()
        await run_git_import(
            task_id=task_id,
            url=str(repo),
            project="calc-proj",
            embedding=emb,
            vector_store=vs,
        )

        task = get_task(task_id)
        assert task["status"] == "done"
        assert await vs.count("calc-proj") > 0

        # Step 2: 检索
        chunks = await retrieve(
            question="Calculator class",
            project="calc-proj",
            top_k=5,
            embedding_client=emb,
            vector_store=vs,
        )

        assert len(chunks) > 0
        assert all(isinstance(c, ScoredChunk) for c in chunks)

        # Step 3: 构建 prompt
        messages = build_prompt("Calculator class 有哪些方法？", chunks)
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "上下文开始" in messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_incremental_reimport(self, e2e_env, tmp_path):
        """增量导入：修改文件后重新导入只处理变更。"""
        vs, emb, repo = e2e_env

        # 第一次导入
        t1 = create_task()
        await run_git_import(
            task_id=t1, url=str(repo), project="inc-e2e",
            embedding=emb, vector_store=vs,
        )
        count_first = await vs.count("inc-e2e")
        assert count_first > 0

        # 第二次导入（无变更）
        t2 = create_task()
        await run_git_import(
            task_id=t2, url=str(repo), project="inc-e2e",
            embedding=emb, vector_store=vs,
        )
        assert get_task(t2)["total"] == 0  # 无变更文件

        # 修改文件后第三次导入
        (repo / "main.py").write_text("def new_func(): pass\n")
        t3 = create_task()
        await run_git_import(
            task_id=t3, url=str(repo), project="inc-e2e",
            embedding=emb, vector_store=vs,
        )
        assert get_task(t3)["total"] >= 1

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_flow(self, e2e_env):
        """多轮对话：导入 → 查询 → 追问，验证 session 上下文传递。"""
        vs, emb, repo = e2e_env

        # 导入
        t = create_task()
        await run_git_import(
            task_id=t, url=str(repo), project="conv-proj",
            embedding=emb, vector_store=vs,
        )

        # 第一轮查询
        chunks1 = await retrieve(
            question="fibonacci 函数",
            project="conv-proj",
            top_k=3,
            embedding_client=emb,
            vector_store=vs,
        )

        store = SessionStore()
        session = store.create("conv-proj")
        session.add_user_message("fibonacci 函数是怎么实现的？")

        messages1 = build_prompt("fibonacci 函数是怎么实现的？", chunks1)
        assert len(messages1) >= 2

        # 模拟助手回答
        session.add_assistant_message("fibonacci 使用递归实现...")

        # 第二轮查询（带历史）
        chunks2 = await retrieve(
            question="时间复杂度",
            project="conv-proj",
            top_k=3,
            embedding_client=emb,
            vector_store=vs,
        )

        history = session.get_history()
        session.add_user_message("它的时间复杂度是多少？")

        messages2 = build_prompt("它的时间复杂度是多少？", chunks2, history=history)
        # system + history(2) + user = 4
        assert len(messages2) == 4
        assert messages2[1]["content"] == "fibonacci 函数是怎么实现的？"


# ---------------------------------------------------------------------------
# E2E: API 层完整流程
# ---------------------------------------------------------------------------


class TestAPIEndToEnd:
    """通过 FastAPI TestClient 测试完整的 API 流程。"""

    @pytest.mark.asyncio
    async def test_api_import_and_query(self, tmp_path):
        """API 层：创建项目 → 导入 → 查询。"""
        repo = _create_test_repo(tmp_path)
        qdrant_client = AsyncQdrantClient(location=":memory:")
        vs = VectorStore(client=qdrant_client)
        emb = FakeEmbedding()

        # 先导入数据
        task_id = create_task()
        await run_git_import(
            task_id=task_id, url=str(repo), project="api-e2e",
            embedding=emb, vector_store=vs,
        )
        assert get_task(task_id)["status"] == "done"

        # 通过 API 查询
        @asynccontextmanager
        async def _lifespan(a):
            a.state.embedding = emb
            a.state.vector_store = vs
            a.state.reranker = None
            a.state.sessions = SessionStore()
            a.state.model_manager = MagicMock()
            a.state.model_manager.list_models.return_value = []
            a.state.model_manager.get_vllm_models = AsyncMock(return_value=[])
            a.state.graph_store = MagicMock()
            a.state.graph_store.get.return_value = None
            yield

        original = app.router.lifespan_context
        app.router.lifespan_context = _lifespan

        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                # 查询（mock LLM 生成）
                with patch("delphi.api.routes.query.generate_sync", new_callable=AsyncMock) as mock_gen:
                    mock_gen.return_value = "Calculator 有 add 和 subtract 方法"
                    resp = c.post("/query", json={"question": "Calculator 有哪些方法", "project": "api-e2e"})

                assert resp.status_code == 200
                data = resp.json()
                assert data["answer"] == "Calculator 有 add 和 subtract 方法"
                assert len(data["sources"]) > 0
        finally:
            app.router.lifespan_context = original
            await vs.close()

    @pytest.mark.asyncio
    async def test_api_stream_query(self, tmp_path):
        """API 层：流式查询端到端。"""
        repo = _create_test_repo(tmp_path)
        qdrant_client = AsyncQdrantClient(location=":memory:")
        vs = VectorStore(client=qdrant_client)
        emb = FakeEmbedding()

        task_id = create_task()
        await run_git_import(
            task_id=task_id, url=str(repo), project="stream-e2e",
            embedding=emb, vector_store=vs,
        )

        @asynccontextmanager
        async def _lifespan(a):
            a.state.embedding = emb
            a.state.vector_store = vs
            a.state.reranker = None
            a.state.sessions = SessionStore()
            a.state.model_manager = MagicMock()
            a.state.model_manager.list_models.return_value = []
            a.state.model_manager.get_vllm_models = AsyncMock(return_value=[])
            a.state.graph_store = MagicMock()
            a.state.graph_store.get.return_value = None
            yield

        original = app.router.lifespan_context
        app.router.lifespan_context = _lifespan

        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                async def _fake_generate(messages, url, model):
                    yield "hello"
                    yield " world"

                with patch("delphi.api.routes.query.generate", side_effect=_fake_generate):
                    resp = c.post("/query/stream", json={"question": "Calculator", "project": "stream-e2e"})

                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")

                events = []
                for line in resp.text.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            pass

                types = [e["type"] for e in events]
                assert "done" in types
        finally:
            app.router.lifespan_context = original
            await vs.close()
