"""Agentic RAG：多步推理与工具调用

使用 ReAct 模式实现 agent loop，LLM 可以调用 search / lookup 工具
进行多步检索，最终综合回答复杂问题。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from delphi.core.config import settings
from delphi.retrieval.rag import generate_sync, retrieve

if TYPE_CHECKING:
    from delphi.core.clients import EmbeddingClient, VectorStore
    from delphi.graph.store import GraphStore
    from delphi.retrieval.rag import RerankerClient

from loguru import logger

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

FORCE_FINAL_ANSWER_PROMPT = "你已经进行了多步检索，请根据已收集到的所有信息，直接给出最终答案。不要再调用工具。"

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


def parse_llm_output(text: str) -> AgentStep:
    """从 LLM 输出中解析 Thought / Action / Answer。

    对格式不规范的输出做容错处理：
    - 如果没有 Thought 标记，把整段文本当作 thought
    - 如果同时出现 Action 和 Answer，优先 Answer
    """
    text = text.strip()
    logger.debug("解析 LLM 输出, 长度={}", len(text))

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

    step = AgentStep(thought=thought, action=action, answer=answer)
    logger.debug(
        "LLM 输出解析完成, has_thought={}, has_action={}, has_answer={}",
        bool(thought), action is not None, answer is not None,
    )
    return step


# ---------------------------------------------------------------------------
# Tool argument parsing
# ---------------------------------------------------------------------------

_SEARCH_RE = re.compile(r"search\s*\(\s*(.+?)\s*\)\s*$", re.IGNORECASE)
_LOOKUP_RE = re.compile(
    r"lookup\s*\(\s*(.+?)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*$",
    re.IGNORECASE,
)


def parse_action(action_str: str) -> tuple[str, list[str]]:
    """解析 Action 字符串，返回 (tool_name, args)。

    支持的格式：
      search(some query)
      search("some query")
      lookup(path/to/file.py, 10, 20)
      lookup("path/to/file.py", 10, 20)
    """
    action_str = action_str.strip()
    logger.debug("解析 Action 字符串: {}", action_str[:100])

    m = _SEARCH_RE.match(action_str)
    if m:
        query = m.group(1).strip().strip("\"'")
        logger.debug("解析为 search 工具, query={}", query[:80])
        return "search", [query]

    m = _LOOKUP_RE.match(action_str)
    if m:
        file_path = m.group(1).strip().strip("\"'")
        start_line = m.group(2)
        end_line = m.group(3)
        logger.debug("解析为 lookup 工具, file={}, lines={}-{}", file_path, start_line, end_line)
        return "lookup", [file_path, start_line, end_line]

    logger.warning("未知 Action 格式: {}", action_str[:100])
    return "unknown", [action_str]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def exec_search(
    query: str,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None,
    top_k: int = settings.chunk_top_k,
    graph_store: GraphStore | None = None,
) -> str:
    """执行 search 工具，返回格式化的检索结果。"""
    logger.info("Agent search 工具执行, query={}, project={}", query[:80], project)
    chunks = await retrieve(
        question=query,
        project=project,
        top_k=top_k,
        embedding_client=embedding_client,
        vector_store=vector_store,
        reranker=reranker,
        graph_store=graph_store,
    )
    if not chunks:
        logger.warning("Agent search 未找到相关内容, query={}", query[:80])
        return "未找到相关内容。"

    logger.debug("Agent search 返回 {} 个结果", len(chunks))

    parts: list[str] = []
    for i, c in enumerate(chunks, 1):
        line_info = ""
        if c.start_line is not None and c.end_line is not None:
            line_info = f" (行 {c.start_line}-{c.end_line})"
        parts.append(f"[{i}] {c.file_path}{line_info}\n{c.content}")
    return "\n\n".join(parts)


async def exec_lookup(
    file_path: str,
    start_line: int,
    end_line: int,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> str:
    """执行 lookup 工具：通过 scroll 过滤 file_path + 行号范围。"""
    logger.info("Agent lookup 工具执行, file={}, lines={}-{}", file_path, start_line, end_line)
    records = await vector_store.scroll_by_file(
        collection=project,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
    )

    matched_chunks: list[str] = []
    for record in records:
        payload = record.payload or {}
        sl = payload.get("start_line")
        el = payload.get("end_line")
        if sl is None or el is None:
            continue
        text = payload.get("text", payload.get("content", ""))
        matched_chunks.append(f"[行 {sl}-{el}]\n{text}")

    if not matched_chunks:
        logger.warning("Agent lookup 未找到内容, file={}, lines={}-{}", file_path, start_line, end_line)
        return f"未找到 {file_path} 中行 {start_line}-{end_line} 的内容。"

    logger.debug("Agent lookup 返回 {} 个代码片段", len(matched_chunks))
    return f"文件: {file_path}\n\n" + "\n\n".join(matched_chunks)


async def exec_tool(
    step: AgentStep,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None = None,
    top_k: int = settings.chunk_top_k,
    graph_store: GraphStore | None = None,
) -> str:
    """执行 agent step 中的工具调用，返回 observation 文本。

    包含工具分发、异常处理和结果截断。
    """
    tool_name, args = parse_action(step.action)
    observation: str
    logger.info("Agent 工具执行开始, tool={}, args={}", tool_name, args[:3] if args else [])

    try:
        if tool_name == "search" and args:
            observation = await exec_search(
                query=args[0],
                project=project,
                embedding_client=embedding_client,
                vector_store=vector_store,
                reranker=reranker,
                top_k=top_k,
                graph_store=graph_store,
            )
        elif tool_name == "lookup" and len(args) == 3:
            observation = await exec_lookup(
                file_path=args[0],
                start_line=int(args[1]),
                end_line=int(args[2]),
                project=project,
                embedding_client=embedding_client,
                vector_store=vector_store,
            )
        else:
            observation = f"未知工具或参数错误: {step.action}"
            logger.warning("Agent 未知工具调用: {}", step.action)
    except Exception as exc:
        logger.error("Agent 工具执行失败, tool={}: {}", tool_name, str(exc), exc_info=True)
        observation = f"工具执行出错: {exc}"

    # 截断过长的 observation，避免上下文溢出
    max_obs_len = 4000
    if len(observation) > max_obs_len:
        logger.debug("Agent 工具结果截断, 原始长度={}, 截断到={}", len(observation), max_obs_len)
        observation = observation[:max_obs_len] + "\n...(结果已截断)"

    logger.debug("Agent 工具执行完成, tool={}, observation_len={}", tool_name, len(observation))
    return observation


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


def build_agent_messages(
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


def build_force_final_messages(
    question: str,
    steps: list[AgentStep],
    history: list[dict] | None = None,
) -> list[dict]:
    """构建强制最终答案的消息列表。"""
    messages = build_agent_messages(question, steps, history)
    messages.append({"role": "user", "content": FORCE_FINAL_ANSWER_PROMPT})
    return messages


async def run_agent(
    question: str,
    project: str,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    reranker: RerankerClient | None = None,
    max_steps: int = 5,
    history: list[dict] | None = None,
    top_k: int = settings.chunk_top_k,
    graph_store: GraphStore | None = None,
) -> tuple[str, list[AgentStep]]:
    """运行 agent loop，返回 (最终答案, 步骤列表)。"""
    steps: list[AgentStep] = []
    logger.info("Agent 推理开始, question={}, project={}, max_steps={}", question[:80], project, max_steps)

    for step_num in range(max_steps):
        messages = build_agent_messages(question, steps, history)
        logger.debug("Agent 第 {} 步, 构建消息 {} 条", step_num + 1, len(messages))

        try:
            llm_output = await generate_sync(messages, settings.vllm_url, settings.llm_model)
        except Exception:
            logger.exception("Agent LLM 调用失败, step={}", step_num + 1)
            break

        step = parse_llm_output(llm_output)

        # 如果 LLM 给出了最终答案
        if step.answer:
            steps.append(step)
            logger.info("Agent 推理完成, 在第 {} 步获得最终答案, 答案长度={}", step_num + 1, len(step.answer))
            return step.answer, steps

        # 如果没有 action，把 thought 当作最终答案
        if not step.action:
            steps.append(step)
            logger.info("Agent 推理完成, 第 {} 步无 action, 以 thought 作为答案", step_num + 1)
            return step.thought, steps

        # 执行工具
        logger.debug("Agent 第 {} 步执行工具: {}", step_num + 1, step.action[:80])
        observation = await exec_tool(
            step, project, embedding_client, vector_store, reranker, top_k,
            graph_store=graph_store,
        )
        step.observation = observation
        steps.append(step)

    # 超过 max_steps，强制用已有信息生成最终答案
    logger.warning("Agent 超过最大步数 {}, 强制生成最终答案, 已执行 {} 步", max_steps, len(steps))
    return await force_final_answer(question, steps, history), steps


async def force_final_answer(
    question: str,
    steps: list[AgentStep],
    history: list[dict] | None = None,
) -> str:
    """超过最大步数时，强制让 LLM 基于已收集信息生成最终答案。"""
    logger.info("强制生成最终答案, 已有 {} 步记录", len(steps))
    messages = build_force_final_messages(question, steps, history)

    try:
        answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)
        logger.info("强制最终答案生成成功, 答案长度={}", len(answer))
    except Exception:
        logger.exception("强制最终答案生成失败")
        # 回退：拼接所有 observation 作为答案
        observations = [s.observation for s in steps if s.observation]
        answer = "根据检索到的信息：\n\n" + "\n\n".join(observations) if observations else "无法生成答案。"
        logger.warning("回退到拼接 observation, 共 {} 条", len(observations))

    return answer
