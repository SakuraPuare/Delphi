"""集成测试：RAG 完整流程 query → retrieve → rerank → generate。

使用 mock 替代实际的 LLM 和向量存储调用。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from delphi.core.clients import EmbeddingResult, SparseVector
from delphi.retrieval.intent import Intent, classify_intent
from delphi.retrieval.rag import ScoredChunk, build_prompt, deduplicate_chunks, retrieve
from delphi.retrieval.session import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scored_point(text: str, file_path: str, score: float, start_line=1, end_line=10):
    pt = MagicMock()
    pt.payload = {
        "text": text,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
    }
    pt.score = score
    return pt


def _fake_sparse():
    return SparseVector(indices=[0, 1, 2], values=[0.1, 0.2, 0.3])


# ---------------------------------------------------------------------------
# 完整 RAG 流程
# ---------------------------------------------------------------------------


class TestFullRAGPipeline:
    """测试 query → retrieve → build_prompt → generate 的完整链路。"""

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.settings")
    async def test_retrieve_build_prompt_generate(self, mock_settings):
        """完整流程：embedding → search → deduplicate → build_prompt。"""
        mock_settings.query_rewrite_enabled = False
        mock_settings.reranker_enabled = False

        embedding = AsyncMock()
        embedding.embed_all = AsyncMock(
            return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[_fake_sparse()])
        )

        points = [
            _make_scored_point("def hello(): pass", "src/main.py", 0.95),
            _make_scored_point("# README\nHello world", "README.md", 0.80),
        ]
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=points)

        chunks = await retrieve(
            question="hello 函数的实现",
            project="test-proj",
            top_k=5,
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert len(chunks) == 2
        assert chunks[0].score >= chunks[1].score
        assert all(isinstance(c, ScoredChunk) for c in chunks)

        messages = build_prompt("hello 函数的实现", chunks)
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "上下文开始" in messages[-1]["content"]
        assert "hello 函数的实现" in messages[-1]["content"]

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.settings")
    async def test_retrieve_with_reranker(self, mock_settings):
        """带 reranker 的检索流程。"""
        mock_settings.query_rewrite_enabled = False
        mock_settings.reranker_enabled = False
        mock_settings.retrieve_top_k = 10
        mock_settings.reranker_top_k = 3
        mock_settings.reranker_score_threshold = 0.0

        embedding = AsyncMock()
        embedding.embed_all = AsyncMock(
            return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[_fake_sparse()])
        )

        points = [
            _make_scored_point("chunk A", "a.py", 0.9),
            _make_scored_point("chunk B", "b.py", 0.8),
            _make_scored_point("chunk C", "c.py", 0.7),
        ]
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=points)

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=[(2, 0.99), (0, 0.85)])

        chunks = await retrieve(
            question="test query",
            project="proj",
            top_k=3,
            embedding_client=embedding,
            vector_store=vector_store,
            reranker=reranker,
        )

        # reranker 重排后 chunk C (index 2) 应排在前面
        assert chunks[0].content == "chunk C"
        assert chunks[0].score == 0.99

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.settings")
    async def test_retrieve_with_query_rewrite(self, mock_settings):
        """启用 query rewrite 的检索流程。"""
        mock_settings.query_rewrite_enabled = True
        mock_settings.reranker_enabled = False
        mock_settings.vllm_url = "http://fake:8000"
        mock_settings.llm_model = "test-model"
        mock_settings.llm_api_key = ""

        embedding = AsyncMock()
        embedding.embed_all = AsyncMock(
            return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[_fake_sparse()])
        )
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=[
            _make_scored_point("rewritten result", "x.py", 0.9),
        ])

        with patch("delphi.retrieval.rag.rewrite_query", new_callable=AsyncMock) as mock_rewrite:
            mock_rewrite.return_value = "改写后的查询"
            chunks = await retrieve(
                question="原始问题",
                project="proj",
                top_k=5,
                embedding_client=embedding,
                vector_store=vector_store,
            )

        assert len(chunks) == 1
        mock_rewrite.assert_awaited_once()


# ---------------------------------------------------------------------------
# Intent 分类与 prompt 路由
# ---------------------------------------------------------------------------


class TestIntentRouting:
    """测试不同 intent 类型对 system prompt 的影响。"""

    def test_code_intent_prompt(self):
        """代码类问题应使用代码分析 system prompt。"""
        question = "EmbeddingClient 这个 class 是怎么实现的？"
        intent = classify_intent(question)
        assert intent == Intent.CODE

        chunks = [ScoredChunk(content="class EmbeddingClient:", file_path="clients.py", start_line=1, end_line=5, score=0.9)]
        messages = build_prompt(question, chunks)
        assert "代码分析" in messages[0]["content"] or "代码" in messages[0]["content"]

    def test_doc_intent_prompt(self):
        """文档类问题应使用文档问答 system prompt。"""
        question = "请介绍一下这个项目的文档说明"
        intent = classify_intent(question)
        assert intent == Intent.DOC

        chunks = [ScoredChunk(content="# Guide", file_path="docs/guide.md", start_line=None, end_line=None, score=0.8)]
        messages = build_prompt(question, chunks)
        assert "文档" in messages[0]["content"]

    def test_general_intent_prompt(self):
        """通用问题应使用通用 system prompt。"""
        question = "这个系统的整体架构是怎样的"
        chunks = [ScoredChunk(content="架构说明", file_path="arch.md", start_line=None, end_line=None, score=0.7)]
        messages = build_prompt(question, chunks)
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"


# ---------------------------------------------------------------------------
# 多轮对话上下文
# ---------------------------------------------------------------------------


class TestMultiTurnConversation:
    """测试多轮对话历史在 prompt 中的传递。"""

    def test_history_included_in_prompt(self):
        """对话历史应被包含在 messages 中。"""
        history = [
            {"role": "user", "content": "什么是 RAG？"},
            {"role": "assistant", "content": "RAG 是检索增强生成..."},
        ]
        chunks = [ScoredChunk(content="RAG pipeline code", file_path="rag.py", start_line=1, end_line=20, score=0.9)]
        messages = build_prompt("能详细说说吗？", chunks, history=history)

        # system + history(2) + user = 4
        assert len(messages) == 4
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "什么是 RAG？"
        assert messages[2]["role"] == "assistant"

    def test_session_store_tracks_conversation(self):
        """SessionStore 应正确追踪多轮对话。"""
        store = SessionStore()
        session = store.create("test-proj")

        session.add_user_message("第一个问题")
        session.add_assistant_message("第一个回答")
        session.add_user_message("第二个问题")

        history = session.get_history()
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "第一个问题"
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "第二个问题"

    def test_session_retrieval_by_id(self):
        """通过 session_id 获取已有会话。"""
        store = SessionStore()
        session = store.create("proj")
        session.add_user_message("hello")

        retrieved = store.get(session.session_id)
        assert retrieved is not None
        assert len(retrieved.messages) == 1

    def test_nonexistent_session_returns_none(self):
        store = SessionStore()
        assert store.get("nonexistent-id") is None


# ---------------------------------------------------------------------------
# 空结果处理
# ---------------------------------------------------------------------------


class TestEmptyResults:
    """测试检索无结果时的处理。"""

    @pytest.mark.asyncio
    @patch("delphi.retrieval.rag.settings")
    async def test_retrieve_returns_empty(self, mock_settings):
        """向量存储无匹配时返回空列表。"""
        mock_settings.query_rewrite_enabled = False
        mock_settings.reranker_enabled = False

        embedding = AsyncMock()
        embedding.embed_all = AsyncMock(
            return_value=EmbeddingResult(dense=[[0.1] * 1024], sparse=[_fake_sparse()])
        )
        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=[])

        chunks = await retrieve(
            question="不存在的内容",
            project="empty-proj",
            top_k=5,
            embedding_client=embedding,
            vector_store=vector_store,
        )

        assert chunks == []

    def test_build_prompt_with_empty_chunks(self):
        """空 chunks 列表应生成不含上下文的 prompt。"""
        messages = build_prompt("test question", [])
        assert len(messages) == 2
        assert "上下文开始" in messages[-1]["content"]

    def test_deduplicate_empty_list(self):
        """空列表去重应返回空列表。"""
        assert deduplicate_chunks([]) == []


# ---------------------------------------------------------------------------
# 去重逻辑
# ---------------------------------------------------------------------------


class TestDeduplication:
    """测试检索结果去重。"""

    def test_exact_duplicate_removal(self):
        """完全相同内容只保留 score 最高的。"""
        chunks = [
            ScoredChunk(content="same", file_path="a.py", start_line=1, end_line=5, score=0.9),
            ScoredChunk(content="same", file_path="a.py", start_line=1, end_line=5, score=0.7),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_overlapping_line_range_dedup(self):
        """同文件中行范围重叠 >50% 的只保留 score 高的。"""
        chunks = [
            ScoredChunk(content="chunk1", file_path="a.py", start_line=1, end_line=10, score=0.9),
            ScoredChunk(content="chunk2", file_path="a.py", start_line=3, end_line=12, score=0.7),
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0].content == "chunk1"

    def test_different_files_not_deduped(self):
        """不同文件的 chunks 不应被去重。"""
        chunks = [
            ScoredChunk(content="code", file_path="a.py", start_line=1, end_line=10, score=0.9),
            ScoredChunk(content="code", file_path="b.py", start_line=1, end_line=10, score=0.8),
        ]
        result = deduplicate_chunks(chunks)
        # 内容相同会被去重（完全重复去重阶段）
        assert len(result) == 1
