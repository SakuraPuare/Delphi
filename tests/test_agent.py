from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from delphi.api.app import app
from delphi.core.clients import EmbeddingResult, SparseVector
from delphi.retrieval.agent import (
    AgentStep,
    _build_agent_messages,
    _parse_action,
    _parse_llm_output,
    run_agent,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_mock_app_state():
    """Return mocked embedding + vector_store attached to app.state."""
    embedding = AsyncMock()
    fake_sparse = SparseVector(indices=[0, 1, 2], values=[0.1, 0.2, 0.3])
    embedding.embed_all = AsyncMock(
        return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[fake_sparse])
    )
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
# _parse_llm_output tests
# ---------------------------------------------------------------------------


class TestParseLlmOutput:
    def test_standard_thought_action(self):
        text = "Thought: 需要搜索相关代码\nAction: search(EmbeddingClient)"
        step = _parse_llm_output(text)
        assert step.thought == "需要搜索相关代码"
        assert step.action == "search(EmbeddingClient)"
        assert step.answer is None

    def test_standard_thought_answer(self):
        text = "Thought: 我已经收集到足够信息\nAnswer: 这个函数在 main.py 第10行"
        step = _parse_llm_output(text)
        assert step.thought == "我已经收集到足够信息"
        assert step.answer == "这个函数在 main.py 第10行"
        assert step.action is None

    def test_answer_takes_priority_over_action(self):
        """当同时出现 Action 和 Answer 时，优先 Answer。"""
        text = "Thought: 分析\nAction: search(foo)\nAnswer: 最终答案"
        step = _parse_llm_output(text)
        assert step.answer == "最终答案"
        assert step.action is None

    def test_no_thought_label(self):
        """没有 Thought 标记时，Action 之前的文本当作 thought。"""
        text = "我来分析一下这个问题\nAction: search(config)"
        step = _parse_llm_output(text)
        assert step.thought == "我来分析一下这个问题"
        assert step.action == "search(config)"

    def test_plain_text_becomes_thought(self):
        """完全没有标记时，整段文本当作 thought。"""
        text = "这是一段没有任何标记的文本"
        step = _parse_llm_output(text)
        assert step.thought == "这是一段没有任何标记的文本"
        assert step.action is None
        assert step.answer is None

    def test_chinese_colon(self):
        """支持中文冒号。"""
        text = "Thought：需要查找\nAction：search(test)"
        step = _parse_llm_output(text)
        assert step.thought == "需要查找"
        assert step.action == "search(test)"

    def test_multiline_answer(self):
        text = "Thought: 总结\nAnswer: 第一行\n第二行\n第三行"
        step = _parse_llm_output(text)
        assert "第一行" in step.answer
        assert "第三行" in step.answer

    def test_empty_input(self):
        step = _parse_llm_output("")
        assert step.thought == ""
        assert step.action is None
        assert step.answer is None

    def test_whitespace_only(self):
        step = _parse_llm_output("   \n  \n  ")
        assert step.thought == ""


# ---------------------------------------------------------------------------
# _parse_action tests
# ---------------------------------------------------------------------------


class TestParseAction:
    def test_search_simple(self):
        name, args = _parse_action("search(EmbeddingClient 配置)")
        assert name == "search"
        assert args == ["EmbeddingClient 配置"]

    def test_search_quoted(self):
        name, args = _parse_action('search("hello world")')
        assert name == "search"
        assert args == ["hello world"]

    def test_lookup_basic(self):
        name, args = _parse_action("lookup(src/main.py, 10, 20)")
        assert name == "lookup"
        assert args == ["src/main.py", "10", "20"]

    def test_lookup_quoted_path(self):
        name, args = _parse_action('lookup("src/main.py", 10, 20)')
        assert name == "lookup"
        assert args == ["src/main.py", "10", "20"]

    def test_unknown_tool(self):
        name, args = _parse_action("foobar(something)")
        assert name == "unknown"

    def test_malformed_input(self):
        name, args = _parse_action("这不是一个合法的工具调用")
        assert name == "unknown"


# ---------------------------------------------------------------------------
# _build_agent_messages tests
# ---------------------------------------------------------------------------


class TestBuildAgentMessages:
    def test_initial_message(self):
        msgs = _build_agent_messages("你好", [], None)
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "你好"

    def test_with_history(self):
        history = [
            {"role": "user", "content": "之前的问题"},
            {"role": "assistant", "content": "之前的回答"},
        ]
        msgs = _build_agent_messages("新问题", [], history)
        assert msgs[1]["content"] == "之前的问题"
        assert msgs[2]["content"] == "之前的回答"
        assert msgs[-1]["content"] == "新问题"

    def test_with_steps(self):
        steps = [
            AgentStep(
                thought="需要搜索",
                action="search(foo)",
                observation="找到了一些结果",
            ),
        ]
        msgs = _build_agent_messages("问题", steps, None)
        # system + user question + assistant step + observation
        assert len(msgs) == 4
        assert "Thought: 需要搜索" in msgs[2]["content"]
        assert "Action: search(foo)" in msgs[2]["content"]
        assert msgs[3]["role"] == "user"
        assert "Observation:" in msgs[3]["content"]



# ---------------------------------------------------------------------------
# run_agent tests
# ---------------------------------------------------------------------------


class TestRunAgent:
    """测试 agent loop 核心逻辑。"""

    @patch("delphi.retrieval.agent.generate_sync")
    async def test_simple_question_direct_answer(self, mock_gen):
        """简单问题直接返回 Answer，不进入工具调用循环。"""
        mock_gen.return_value = (
            "Thought: 这个问题我可以直接回答\n"
            "Answer: hello 函数定义在 main.py 第1行"
        )
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="hello 函数在哪里？",
            project="test_project",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert "hello" in answer
        assert len(steps) == 1
        assert steps[0].answer is not None
        assert steps[0].action is None
        # LLM 只被调用一次
        assert mock_gen.call_count == 1

    @patch("delphi.retrieval.agent.retrieve")
    @patch("delphi.retrieval.agent.generate_sync")
    async def test_complex_question_agent_loop(self, mock_gen, mock_retrieve):
        """复杂问题触发 agent loop：search -> 得到结果 -> 最终回答。"""
        from delphi.retrieval.rag import ScoredChunk

        # 第一次调用：LLM 决定搜索
        # 第二次调用：LLM 给出最终答案
        mock_gen.side_effect = [
            "Thought: 需要搜索相关代码\nAction: search(EmbeddingClient 配置)",
            "Thought: 找到了相关信息\nAnswer: EmbeddingClient 在 config.py 中配置",
        ]
        mock_retrieve.return_value = [
            ScoredChunk(
                content="class EmbeddingClient:\n    pass",
                file_path="src/config.py",
                start_line=1,
                end_line=2,
                score=0.9,
            ),
        ]
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="EmbeddingClient 怎么配置？",
            project="test_project",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert "EmbeddingClient" in answer
        assert len(steps) == 2
        assert steps[0].action is not None
        assert steps[0].observation is not None
        assert steps[1].answer is not None
        assert mock_gen.call_count == 2


    @patch("delphi.retrieval.agent.retrieve")
    @patch("delphi.retrieval.agent.generate_sync")
    async def test_search_tool_call(self, mock_gen, mock_retrieve):
        """search 工具被正确调用并返回格式化结果。"""
        from delphi.retrieval.rag import ScoredChunk

        mock_gen.side_effect = [
            "Thought: 搜索一下\nAction: search(vector store)",
            "Thought: 够了\nAnswer: 找到了",
        ]
        mock_retrieve.return_value = [
            ScoredChunk(
                content="class VectorStore: ...",
                file_path="src/store.py",
                start_line=10,
                end_line=20,
                score=0.88,
            ),
        ]
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="VectorStore 在哪？",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        # retrieve 被调用，参数包含 search query
        mock_retrieve.assert_called_once()
        call_kwargs = mock_retrieve.call_args
        assert call_kwargs.kwargs["question"] == "vector store"
        # observation 包含文件路径信息
        assert "src/store.py" in steps[0].observation

    @patch("delphi.retrieval.agent.generate_sync")
    async def test_lookup_tool_call(self, mock_gen):
        """lookup 工具被正确调用，通过 qdrant 检索特定文件行号。"""
        mock_gen.side_effect = [
            "Thought: 查看具体代码\nAction: lookup(src/main.py, 10, 20)",
            "Thought: 看到了\nAnswer: 这段代码做了初始化",
        ]
        embedding, vector_store = _make_mock_app_state()

        # mock qdrant client 的 query_points 返回
        mock_point = MagicMock()
        mock_point.payload = {
            "content": "def init():\n    pass",
            "file_path": "src/main.py",
            "start_line": 10,
            "end_line": 15,
        }
        mock_query_result = MagicMock()
        mock_query_result.points = [mock_point]
        vector_store._client = AsyncMock()
        vector_store._client.query_points = AsyncMock(return_value=mock_query_result)

        answer, steps = await run_agent(
            question="main.py 第10-20行是什么？",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert len(steps) == 2
        assert steps[0].action == "lookup(src/main.py, 10, 20)"
        assert "src/main.py" in steps[0].observation
        # embedding.embed_all 被调用（lookup 需要 embedding）
        embedding.embed_all.assert_called()


    @patch("delphi.retrieval.agent.retrieve")
    @patch("delphi.retrieval.agent.generate_sync")
    async def test_max_steps_force_termination(self, mock_gen, mock_retrieve):
        """超过 max_steps 时强制终止并生成最终答案。"""
        from delphi.retrieval.rag import ScoredChunk

        # LLM 每次都返回 action，永远不给 answer
        mock_gen.side_effect = [
            "Thought: 搜索第一次\nAction: search(query1)",
            "Thought: 搜索第二次\nAction: search(query2)",
            # 第三次调用是 _force_final_answer
            "根据已有信息，答案是这样的",
        ]
        mock_retrieve.return_value = [
            ScoredChunk(
                content="some content",
                file_path="a.py",
                start_line=1,
                end_line=5,
                score=0.8,
            ),
        ]
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="复杂问题",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
            max_steps=2,
        )

        # 执行了 2 步工具调用后被强制终止
        assert len(steps) == 2
        # 最终答案由 _force_final_answer 生成
        assert answer is not None
        assert len(answer) > 0

    @patch("delphi.retrieval.agent.generate_sync")
    async def test_no_action_returns_thought_as_answer(self, mock_gen):
        """LLM 输出没有 Action 也没有 Answer 时，thought 作为最终答案。"""
        mock_gen.return_value = "这个问题的答案很简单，不需要工具"
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="简单问题",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert answer == "这个问题的答案很简单，不需要工具"
        assert len(steps) == 1
        assert steps[0].action is None
        assert steps[0].answer is None

    @patch("delphi.retrieval.agent.generate_sync")
    async def test_llm_exception_breaks_loop(self, mock_gen):
        """LLM 调用异常时，loop 中断并走 _force_final_answer。"""
        mock_gen.side_effect = Exception("vLLM 服务不可用")
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="任何问题",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        # 没有步骤被记录（异常发生在第一步）
        assert len(steps) == 0
        # 仍然返回了答案（_force_final_answer 的 fallback）
        assert answer is not None

    @patch("delphi.retrieval.agent.retrieve")
    @patch("delphi.retrieval.agent.generate_sync")
    async def test_observation_truncation(self, mock_gen, mock_retrieve):
        """过长的 observation 被截断到 4000 字符。"""
        from delphi.retrieval.rag import ScoredChunk

        mock_gen.side_effect = [
            "Thought: 搜索\nAction: search(big result)",
            "Thought: 好的\nAnswer: 完成",
        ]
        # 返回一个超长内容的 chunk
        mock_retrieve.return_value = [
            ScoredChunk(
                content="x" * 5000,
                file_path="big.py",
                start_line=1,
                end_line=100,
                score=0.9,
            ),
        ]
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="大结果",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert len(steps[0].observation) <= 4000 + len("\n...(结果已截断)")
        assert steps[0].observation.endswith("...(结果已截断)")

    @patch("delphi.retrieval.agent.generate_sync")
    async def test_unknown_tool_observation(self, mock_gen):
        """未知工具名产生错误 observation 而非异常。"""
        mock_gen.side_effect = [
            "Thought: 试试\nAction: foobar(something)",
            "Thought: 好吧\nAnswer: 无法使用该工具",
        ]
        embedding, vector_store = _make_mock_app_state()

        answer, steps = await run_agent(
            question="测试",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert "未知工具" in steps[0].observation
        assert len(steps) == 2

    @patch("delphi.retrieval.agent.retrieve")
    @patch("delphi.retrieval.agent.generate_sync")
    async def test_with_session_history(self, mock_gen, mock_retrieve):
        """传入 history 时，消息列表包含历史对话。"""
        mock_gen.return_value = "Thought: 了解\nAnswer: 基于上下文的回答"
        embedding, vector_store = _make_mock_app_state()

        history = [
            {"role": "user", "content": "之前的问题"},
            {"role": "assistant", "content": "之前的回答"},
        ]

        answer, steps = await run_agent(
            question="后续问题",
            project="proj",
            embedding_client=embedding,
            vector_store=vector_store,
            history=history,
        )

        # 验证 generate_sync 收到的 messages 包含 history
        call_args = mock_gen.call_args
        messages = call_args.args[0] if call_args.args else call_args.kwargs.get("messages")
        # system + 2 history + user question = 4
        assert len(messages) == 4
        assert messages[1]["content"] == "之前的问题"




# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------


class TestAgentQueryRoute:
    @patch("delphi.retrieval.agent.generate_sync")
    def test_post_agent_query_success(self, mock_gen, client):
        """POST /agent/query 正常返回结构化响应。"""
        mock_gen.return_value = (
            "Thought: 直接回答\nAnswer: 这是答案"
        )
        resp = client.post(
            "/agent/query",
            json={"question": "测试问题", "project": "proj"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert data["answer"] == "这是答案"
        assert "steps" in data
        assert len(data["steps"]) == 1
        assert data["steps"][0]["thought"] == "直接回答"
        assert data["session_id"] is not None

    def test_post_agent_query_empty_question(self, client):
        """空问题返回 400。"""
        resp = client.post(
            "/agent/query",
            json={"question": "   ", "project": "proj"},
        )
        assert resp.status_code == 400

    @patch("delphi.retrieval.agent.retrieve")
    @patch("delphi.retrieval.agent.generate_sync")
    def test_post_agent_query_with_tool_steps(self, mock_gen, mock_retrieve, client):
        """POST /agent/query 包含工具调用步骤时返回完整 steps。"""
        from delphi.retrieval.rag import ScoredChunk

        mock_gen.side_effect = [
            "Thought: 需要搜索\nAction: search(config)",
            "Thought: 找到了\nAnswer: 配置在 config.py",
        ]
        mock_retrieve.return_value = [
            ScoredChunk(
                content="settings = ...",
                file_path="src/config.py",
                start_line=1,
                end_line=3,
                score=0.9,
            ),
        ]
        resp = client.post(
            "/agent/query",
            json={"question": "配置在哪？", "project": "proj"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["steps"]) == 2
        assert data["steps"][0]["action"] is not None
        assert data["steps"][0]["observation"] is not None
        assert data["steps"][1]["answer"] is not None
        # sources 应包含从 observation 中提取的文件
        assert len(data["sources"]) >= 1
        assert data["sources"][0]["file"] == "src/config.py"

    @patch("delphi.retrieval.agent.generate_sync")
    def test_post_agent_query_session_continuity(self, mock_gen, client):
        """使用 session_id 实现多轮对话。"""
        mock_gen.return_value = "Thought: ok\nAnswer: 第一轮回答"
        resp1 = client.post(
            "/agent/query",
            json={"question": "第一个问题", "project": "proj"},
        )
        assert resp1.status_code == 200
        session_id = resp1.json()["session_id"]
        assert session_id is not None

        mock_gen.return_value = "Thought: ok\nAnswer: 第二轮回答"
        resp2 = client.post(
            "/agent/query",
            json={
                "question": "后续问题",
                "project": "proj",
                "session_id": session_id,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["session_id"] == session_id

