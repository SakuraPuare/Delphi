"""Agent 查询路由：多步推理 RAG"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from delphi.api.models import AgentQueryRequest, AgentQueryResponse, AgentStepModel, Source
from delphi.core.config import settings
from delphi.retrieval.agent import (
    AgentStep,
    build_agent_messages,
    build_force_final_messages,
    exec_tool,
    parse_action,
    parse_llm_output,
    run_agent,
)
from delphi.retrieval.rag import generate, generate_sync

router = APIRouter(prefix="/agent", tags=["agent"])


def _steps_to_models(steps: list[AgentStep]) -> list[AgentStepModel]:
    return [
        AgentStepModel(
            thought=s.thought,
            action=s.action,
            observation=s.observation,
            answer=s.answer,
        )
        for s in steps
    ]


def _collect_sources(steps: list[AgentStep]) -> list[Source]:
    """从 agent 步骤的 observation 中提取来源信息。"""
    sources: list[Source] = []
    seen: set[str] = set()
    idx = 1
    for step in steps:
        if not step.observation or step.observation.startswith("未找到"):
            continue
        # 从 observation 中解析文件路径
        for line in step.observation.split("\n"):
            line = line.strip()
            if line.startswith("[") and "]" in line:
                # 格式: [1] path/to/file (行 X-Y)
                rest = line.split("]", 1)[-1].strip()
                parts = rest.split("(行", 1)
                file_path = parts[0].strip()
                if not file_path or file_path in seen:
                    continue
                seen.add(file_path)
                sources.append(Source(index=idx, file=file_path))
                idx += 1
            elif line.startswith("文件:"):
                file_path = line[len("文件:") :].strip()
                if file_path and file_path not in seen:
                    seen.add(file_path)
                    sources.append(Source(index=idx, file=file_path))
                    idx += 1
    return sources


@router.post("/query", response_model=AgentQueryResponse)
async def agent_query(body: AgentQueryRequest, request: Request) -> AgentQueryResponse:
    """非流式 agent 查询：多步推理后返回完整结果。"""
    logger.info(
        "收到 Agent 查询请求, project={}, question={}, max_steps={}", body.project, body.question[:80], body.max_steps
    )
    t_start = time.monotonic()

    if not body.question.strip():
        logger.warning("Agent 查询请求被拒绝: question 为空")
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
    graph_store = request.app.state.graph_store
    sessions = request.app.state.sessions

    # Session 管理
    session = None
    history = None
    if body.session_id:
        session = sessions.get(body.session_id)
        logger.debug("加载已有 Agent 会话, session_id={}, found={}", body.session_id, session is not None)
    if session is None and body.session_id is None:
        session = sessions.create(body.project)
        logger.debug("创建新 Agent 会话, session_id={}", session.session_id)

    if session:
        history = session.get_history()
        session.add_user_message(body.question)

    session_id = session.session_id if session else None

    answer, steps = await run_agent(
        question=body.question,
        project=body.project,
        embedding_client=embedding_client,
        vector_store=vector_store,
        reranker=reranker,
        max_steps=body.max_steps,
        history=history,
        graph_store=graph_store,
    )
    logger.debug("Agent 推理完成, 步骤数={}", len(steps))

    if session:
        session.add_assistant_message(answer)

    sources = _collect_sources(steps)

    elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
    logger.info(
        "Agent 查询完成, project={}, 耗时={}ms, 步骤数={}, 来源数={}",
        body.project,
        elapsed_ms,
        len(steps),
        len(sources),
    )

    return AgentQueryResponse(
        answer=answer,
        steps=_steps_to_models(steps),
        sources=sources,
        session_id=session_id,
    )


@router.post("/query/stream")
async def agent_query_stream(body: AgentQueryRequest, request: Request):
    """流式 agent 查询：通过 SSE 实时推送推理过程和最终答案。"""
    logger.info(
        "收到 Agent 流式查询请求, project={}, question={}, max_steps={}",
        body.project,
        body.question[:80],
        body.max_steps,
    )

    if not body.question.strip():
        logger.warning("Agent 流式查询请求被拒绝: question 为空")
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
    graph_store = request.app.state.graph_store
    sessions = request.app.state.sessions

    # Session 管理
    session = None
    history = None
    if body.session_id:
        session = sessions.get(body.session_id)
    if session is None and body.session_id is None:
        session = sessions.create(body.project)

    if session:
        history = session.get_history()
        session.add_user_message(body.question)

    session_id = session.session_id if session else None

    async def event_stream():
        steps: list[AgentStep] = []
        max_steps = body.max_steps

        for step_num in range(max_steps):
            logger.debug("Agent 流式推理第 {} 步开始", step_num + 1)
            messages = build_agent_messages(body.question, steps, history)

            try:
                llm_output = await generate_sync(messages, settings.vllm_url, settings.llm_model)
            except Exception:
                logger.exception("Agent LLM 调用失败, step={}", step_num)
                break

            step = parse_llm_output(llm_output)

            # 发送 thought
            if step.thought:
                logger.debug("Agent step {} thought: {}", step_num + 1, step.thought[:100])
                yield _sse({"type": "thought", "content": step.thought})

            # 如果有最终答案，流式输出
            if step.answer:
                logger.debug("Agent step {} 产生最终答案", step_num + 1)
                steps.append(step)
                for char in step.answer:
                    yield _sse({"type": "token", "content": char})
                break

            # 如果没有 action，把 thought 当答案
            if not step.action:
                logger.debug("Agent step {} 无 action, 将 thought 作为答案", step_num + 1)
                steps.append(step)
                for char in step.thought:
                    yield _sse({"type": "token", "content": char})
                break

            # 发送 action 事件
            tool_name, _args = parse_action(step.action)
            logger.debug("Agent step {} 执行工具: {}", step_num + 1, tool_name)
            yield _sse({"type": "action", "tool": tool_name, "args": step.action})

            # 执行工具（复用核心逻辑）
            observation = await exec_tool(
                step,
                body.project,
                embedding_client,
                vector_store,
                reranker,
                graph_store=graph_store,
            )
            step.observation = observation
            steps.append(step)

            yield _sse({"type": "observation", "content": observation})
        else:
            # 超过 max_steps，流式生成最终答案
            logger.warning("Agent 达到最大步数 {}, 强制生成最终答案", max_steps)
            messages = build_force_final_messages(body.question, steps, history)
            yield _sse({"type": "thought", "content": "已达到最大步数，正在综合已有信息生成答案..."})
            forced_answer_parts: list[str] = []
            async for token in generate(messages, settings.vllm_url, settings.llm_model):
                forced_answer_parts.append(token)
                yield _sse({"type": "token", "content": token})
            # 将强制生成的答案存入最后一个 step，以便后续保存到 session
            forced_answer = "".join(forced_answer_parts)
            if steps:
                steps[-1].answer = forced_answer
            else:
                forced_step = AgentStep(thought="已达到最大步数", answer=forced_answer)
                steps.append(forced_step)

        # 记录到 session
        if session:
            # 收集最终答案
            final_answer = ""
            for s in reversed(steps):
                if s.answer:
                    final_answer = s.answer
                    break
            if not final_answer and steps:
                final_answer = steps[-1].thought
            session.add_assistant_message(final_answer)

        # 发送 sources
        sources = _collect_sources(steps)
        if sources:
            yield _sse(
                {
                    "type": "sources",
                    "sources": [s.model_dump() for s in sources],
                }
            )

        logger.info("Agent 流式查询完成, 步骤数={}, 来源数={}", len(steps), len(sources))
        yield _sse({"type": "done", "session_id": session_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    """格式化 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
