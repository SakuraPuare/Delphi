"""Agentic RAG：多步推理与工具调用

使用 ReAct 模式实现 agent loop，LLM 可以调用 search / lookup 工具
进行多步检索，最终综合回答复杂问题。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from delphi.core.config import settings
from delphi.retrieval.rag import generate_sync, retrieve

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.retrieval.rag import RerankerClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """\
你是一个代码与文档分析助手，可以使用以下工具来回答问题：

工具：
1. search(query) - 在知识库中搜索相关内容
2. lookup(file_path, start_line, end_line) - 查看特定文件的代码片段

使用格式：
Thought: 分析当前情况，决定下一步
Action: tool_name(args)

当你有足够信息回答时：
Thought: 我已经收集到足够信息
Answer: 你的最终回答

重要规则：
- 每次只能调用一个工具
- search 的参数是搜索查询字符串
- lookup 的参数是 file_path, start_line, end_line（行号为整数）
- 仔细分析每次工具返回的结果，决定是否需要进一步检索
- 回答时引用具体的文件路径和行号"""

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AgentStep:
    """Agent 单步执行记录。"""

    thought: str
    action: str | None = None
    observation: str | None = None
    answer: str | None = None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_THOUGHT_RE = re.compile(r"Thought\s*[:：]\s*(.+?)(?=\n(?:Action|Answer)\s*[:：]|\Z)", re.DOTALL)
_ACTION_RE = re.compile(r"Action\s*[:：]\s*(.+?)(?=\n|$)")
_ANSWER_RE = re.compile(r"Answer\s*[:：]\s*(.+)", re.DOTALL)


def _parse_llm_output(text: str) -> AgentStep:
    """从 LLM 输出中解析 Thought / Action / Answer。

    对格式不规范的输出做容错处理：
    - 如果没有 Thought 标记，把整段文本当作 thought
    - 如果同时出现 Action 和 Answer，优先 Answer
    """
    text = text.strip()

    thought = ""
    action = None
    answer = None

    thought_m = _THOUGHT_RE.search(text)
    if thought_m:
        thought = thought_m.group(1).strip()
    else:
        # 没有 Thought 标记时，取 Action/Answer 之前的所有文本
        first_label = re.search(r"(Action|Answer)\s*[:：]", text)
        thought = text[: first_label.start()].strip() if first_label else text

    answer_m = _ANSWER_RE.search(text)
    if answer_m:
        answer = answer_m.group(1).strip()
    else:
        action_m = _ACTION_RE.search(text)
        if action_m:
            action = action_m.group(1).strip()

    return AgentStep(thought=thought, action=action, answer=answer)


# ---------------------------------------------------------------------------
# Tool argument parsing
# ---------------------------------------------------------------------------

_SEARCH_RE = re.compile(r"search\s*\(\s*(.+?)\s*\)\s*$", re.IGNORECASE)
_LOOKUP_RE = re.compile(
    r"lookup\s*\(\s*(.+?)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*$",
    re.IGNORECASE,
)


def _parse_action(action_str: str) -> tuple[str, list[str]]:
    """解析 Action 字符串，返回 (tool_name, args)。

    支持的格式：
      search(some query)
      search("some query")
      lookup(path/to/file.py, 10, 20)
      lookup("path/to/file.py", 10, 20)
    """
    action_str = action_str.strip()

    m = _SEARCH_RE.match(action_str)
    if m:
        query = m.group(1).strip().strip("\"'")
        return "search", [query]

    m = _LOOKUP_RE.match(action_str)
    if m:
        file_path = m.group(1).strip().strip("\"'")
        start_line = m.group(2)
        end_line = m.group(3)
        return "lookup", [file_path, start_line, end_line]

    return "unknown", [action_str]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def _exec_search(
    query: str,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None,
) -> str:
    """执行 search 工具，返回格式化的检索结果。"""
    chunks = await retrieve(
        question=query,
        project=project,
        top_k=settings.chunk_top_k,
        embedding_client=embedding_client,
        vector_store=vector_store,
        reranker=reranker,
    )
    if not chunks:
        return "未找到相关内容。"

    parts: list[str] = []
    for i, c in enumerate(chunks, 1):
        line_info = ""
        if c.start_line is not None and c.end_line is not None:
            line_info = f" (行 {c.start_line}-{c.end_line})"
        parts.append(f"[{i}] {c.file_path}{line_info}\n{c.content}")
    return "\n\n".join(parts)


async def _exec_lookup(
    file_path: str,
    start_line: int,
    end_line: int,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> str:
    """执行 lookup 工具：通过向量检索 + file_path 过滤 + 行号范围筛选。"""
    from qdrant_client import models as qmodels

    # 用 file_path 作为查询文本来获取 embedding
    embed_result = await embedding_client.embed_all([file_path])
    query_vector = embed_result.dense[0]

    # 带 file_path 过滤的检索
    collection = project
    client = vector_store._client  # noqa: SLF001
    result = await client.query_points(
        collection_name=collection,
        prefetch=[
            qmodels.Prefetch(
                query=query_vector,
                using="dense",
                limit=50,
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="file_path", match=qmodels.MatchValue(value=file_path))]
                ),
            ),
        ],
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=50,
    )

    # 按行号范围过滤
    matched_chunks: list[str] = []
    for point in result.points:
        payload = point.payload or {}
        sl = payload.get("start_line")
        el = payload.get("end_line")
        if sl is None or el is None:
            continue
        # 有交集即保留
        if sl <= end_line and el >= start_line:
            text = payload.get("text", payload.get("content", ""))
            matched_chunks.append(f"[行 {sl}-{el}]\n{text}")

    if not matched_chunks:
        return f"未找到 {file_path} 中行 {start_line}-{end_line} 的内容。"

    return f"文件: {file_path}\n\n" + "\n\n".join(matched_chunks)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def _build_agent_messages(
    question: str,
    steps: list[AgentStep],
    history: list[dict] | None = None,
) -> list[dict]:
    """构建 agent 对话消息列表。"""
    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    for step in steps:
        # 把每步的 thought + action 作为 assistant 消息
        parts = []
        if step.thought:
            parts.append(f"Thought: {step.thought}")
        if step.action:
            parts.append(f"Action: {step.action}")
        if step.answer:
            parts.append(f"Answer: {step.answer}")
        messages.append({"role": "assistant", "content": "\n".join(parts)})

        # observation 作为 user 消息（模拟工具返回）
        if step.observation is not None:
            messages.append({"role": "user", "content": f"Observation:\n{step.observation}"})

    return messages


async def run_agent(
    question: str,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None = None,
    max_steps: int = 5,
    history: list[dict] | None = None,
) -> tuple[str, list[AgentStep]]:
    """运行 agent loop，返回 (最终答案, 步骤列表)。"""
    steps: list[AgentStep] = []

    for step_num in range(max_steps):
        messages = _build_agent_messages(question, steps, history)

        try:
            llm_output = await generate_sync(messages, settings.vllm_url, settings.llm_model)
        except Exception:
            logger.exception("Agent LLM call failed at step %d", step_num)
            break

        step = _parse_llm_output(llm_output)

        # 如果 LLM 给出了最终答案
        if step.answer:
            steps.append(step)
            return step.answer, steps

        # 如果没有 action，把 thought 当作最终答案
        if not step.action:
            steps.append(step)
            return step.thought, steps

        # 执行工具
        tool_name, args = _parse_action(step.action)
        observation: str

        try:
            if tool_name == "search" and args:
                observation = await _exec_search(
                    query=args[0],
                    project=project,
                    embedding_client=embedding_client,
                    vector_store=vector_store,
                    reranker=reranker,
                )
            elif tool_name == "lookup" and len(args) == 3:
                observation = await _exec_lookup(
                    file_path=args[0],
                    start_line=int(args[1]),
                    end_line=int(args[2]),
                    project=project,
                    embedding_client=embedding_client,
                    vector_store=vector_store,
                )
            else:
                observation = f"未知工具或参数错误: {step.action}"
        except Exception as exc:
            logger.warning("Tool execution failed: %s", exc, exc_info=True)
            observation = f"工具执行出错: {exc}"

        # 截断过长的 observation，避免上下文溢出
        max_obs_len = 4000
        if len(observation) > max_obs_len:
            observation = observation[:max_obs_len] + "\n...(结果已截断)"

        step.observation = observation
        steps.append(step)

    # 超过 max_steps，强制用已有信息生成最终答案
    return await _force_final_answer(question, steps, history), steps


async def _force_final_answer(
    question: str,
    steps: list[AgentStep],
    history: list[dict] | None = None,
) -> str:
    """超过最大步数时，强制让 LLM 基于已收集信息生成最终答案。"""
    messages = _build_agent_messages(question, steps, history)
    messages.append(
        {
            "role": "user",
            "content": "你已经进行了多步检索，请根据已收集到的所有信息，直接给出最终答案。不要再调用工具。",
        }
    )

    try:
        answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)
    except Exception:
        logger.exception("Force final answer failed")
        # 回退：拼接所有 observation 作为答案
        observations = [s.observation for s in steps if s.observation]
        answer = "根据检索到的信息：\n\n" + "\n\n".join(observations) if observations else "无法生成答案。"

    return answer
