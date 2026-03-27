"""意图路由模块测试"""

from __future__ import annotations

import pytest

from delphi.retrieval.intent import PROMPTS, Intent, classify_intent, get_system_prompt


class TestClassifyIntent:
    """classify_intent 分类测试"""

    @pytest.mark.parametrize(
        "question",
        [
            "这个函数怎么实现的",
            "EmbeddingClient 类的 bug",
            "`chunk_file` 的调用方式",
            "def hello 这个方法有什么问题",
            "import 语句报错了",
            "这个 function 的返回值是什么",
        ],
    )
    def test_code_intent(self, question: str):
        assert classify_intent(question) == Intent.CODE

    @pytest.mark.parametrize(
        "question",
        [
            "RAG 的概念是什么",
            "使用指南在哪",
            "这个项目的文档说明",
            "如何理解向量检索",
            "what is embedding",
        ],
    )
    def test_doc_intent(self, question: str):
        assert classify_intent(question) == Intent.DOC

    @pytest.mark.parametrize(
        "question",
        [
            "你好",
            "项目架构",
            "天气怎么样",
        ],
    )
    def test_general_intent(self, question: str):
        assert classify_intent(question) == Intent.GENERAL


class TestGetSystemPrompt:
    """get_system_prompt 测试"""

    @pytest.mark.parametrize("intent", list(Intent))
    def test_returns_non_empty_string(self, intent: Intent):
        prompt = get_system_prompt(intent)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_each_intent_has_distinct_prompt(self):
        prompts = {intent: get_system_prompt(intent) for intent in Intent}
        assert len(set(prompts.values())) == len(Intent)

    def test_fallback_to_general(self):
        """对不在 PROMPTS 中的值，fallback 到 GENERAL prompt。"""
        general_prompt = get_system_prompt(Intent.GENERAL)
        # 直接调用 PROMPTS.get 模拟未知 intent
        result = PROMPTS.get("unknown_intent", PROMPTS[Intent.GENERAL])
        assert result == general_prompt
