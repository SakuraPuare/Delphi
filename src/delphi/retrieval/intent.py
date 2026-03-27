"""意图识别与路由"""
from __future__ import annotations

import logging
import re
from enum import StrEnum

logger = logging.getLogger(__name__)


class Intent(StrEnum):
    CODE = "code"  # 代码相关问答（函数实现、bug 分析、代码解释）
    DOC = "doc"  # 文档相关问答（概念解释、使用指南）
    GENERAL = "general"  # 通用问答（架构设计、最佳实践）


# 关键词规则（快速分类，不依赖 LLM）
# 注意：\b 不适用于中文字符，中文关键词直接匹配即可
# 关键词模式（case-insensitive 匹配）
_CODE_KEYWORD_PATTERNS = [
    r"(函数|方法|接口|变量|参数|返回值|定义|调用|bug|报错|异常|error)",
    r"\b(function|class|method|def|import|return|error|exception|bug|implement)\b",
]

# 代码风格模式（case-sensitive，检测标识符）
_CODE_STYLE_PATTERNS = [
    r"[A-Z][a-z]+[A-Z]",  # CamelCase
    r"[a-z]+_[a-z]+",  # snake_case
    r"`[^`]+`",  # 行内代码
]

_DOC_PATTERNS = [
    r"(文档|说明|指南|教程|概念|原理|介绍|是什么|什么是|如何理解)",
    r"\b(document|guide|tutorial|concept|explain|what is|how to understand)\b",
]


def classify_intent(question: str) -> Intent:
    """基于关键词规则快速分类用户意图。"""
    code_score = sum(
        1 for p in _CODE_KEYWORD_PATTERNS if re.search(p, question, re.IGNORECASE)
    ) + sum(1 for p in _CODE_STYLE_PATTERNS if re.search(p, question))
    doc_score = sum(1 for p in _DOC_PATTERNS if re.search(p, question, re.IGNORECASE))

    if code_score > doc_score:
        return Intent.CODE
    elif doc_score > code_score:
        return Intent.DOC
    else:
        return Intent.GENERAL


# 不同意图的 system prompt
PROMPTS: dict[Intent, str] = {
    Intent.CODE: (
        "你是一个代码分析助手。请根据以下检索到的代码片段回答用户的问题。\n\n"
        "规则：\n"
        "- 只基于提供的代码上下文回答，不要编造信息\n"
        "- 解释代码逻辑时，引用具体的函数名、类名和行号\n"
        "- 如果涉及 bug 或错误，分析可能的原因并给出修复建议\n"
        "- 代码示例使用代码块格式，标注语言和来源文件\n"
        '- 如果上下文中没有足够信息，明确说明"根据现有代码，无法回答该问题"'
    ),
    Intent.DOC: (
        "你是一个文档问答助手。请根据以下检索到的文档内容回答用户的问题。\n\n"
        "规则：\n"
        "- 只基于提供的文档上下文回答，不要编造信息\n"
        "- 用清晰易懂的语言解释概念\n"
        "- 引用具体的文档章节和来源\n"
        "- 如果有相关的代码示例，一并展示\n"
        '- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"'
    ),
    Intent.GENERAL: (
        "你是一个代码与文档问答助手。请根据以下检索到的上下文内容回答用户的问题。\n\n"
        "规则：\n"
        "- 只基于提供的上下文回答，不要编造信息\n"
        '- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"\n'
        "- 回答时引用具体的文件或章节名称\n"
        "- 代码示例使用代码块格式"
    ),
}


def get_system_prompt(intent: Intent) -> str:
    """根据意图返回对应的 system prompt。"""
    return PROMPTS.get(intent, PROMPTS[Intent.GENERAL])
