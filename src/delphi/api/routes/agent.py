"""Agent 查询路由：多步推理 RAG"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from delphi.api.models import AgentQueryRequest, AgentQueryResponse, AgentStepModel, Source
from delphi.core.config import settings
from delphi.retrieval.agent import (
    AgentStep,
    _build_agent_messages,
    _exec_lookup,
    _exec_search,
    _parse_action,
    _parse_llm_output,
    run_agent,
)
from delphi.retrieval.rag import generate, generate_sync

logger = logging.getLogger(__name__)

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
    if not body.question.strip():
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
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

    answer, steps = await run_agent(
        question=body.question,
        project=body.project,
        embedding_client=embedding_client,
        vector_store=vector_store,
        reranker=reranker,
        max_steps=body.max_steps,
        history=history,
    )

    if session:
        session.add_assistant_message(answer)

    sources = _collect_sources(steps)

    return AgentQueryResponse(
        answer=answer,
        steps=_steps_to_models(steps),
        sources=sources,
        session_id=session_id,
    )


@router.post("/query/stream")
async def agent_query_stream(body: AgentQueryRequest, request: Request):
    """流式 agent 查询：通过 SSE 实时推送推理过程和最终答案。"""
    if not body.question.strip():
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
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
            messages = _build_agent_messages(body.question, steps, history)

            try:
                llm_output = await generate_sync(messages, settings.vllm_url, settings.llm_model)
            except Exception:
                logger.exception("Agent LLM call failed at step %d", step_num)
                break

            step = _parse_llm_output(llm_output)

            # 发送 thought
            if step.thought:
                yield _sse({"type": "thought", "content": step.thought})

            # 如果有最终答案，流式输出
            if step.answer:
                steps.append(step)
                # 流式输出最终答案的每个 token
                for char in step.answer:
                    yield _sse({"type": "token", "content": char})
                break

            # 如果没有 action，把 thought 当答案
            if not step.action:
                steps.append(step)
                for char in step.thought:
                    yield _sse({"type": "token", "content": char})
                break

            # 发送 action 事件
            tool_name, args = _parse_action(step.action)
            yield _sse({"type": "action", "tool": tool_name, "args": step.action})

            # 执行工具
            try:
                if tool_name == "search" and args:
                    observation = await _exec_search(
                        query=args[0],
                        project=body.project,
                        embedding_client=embedding_client,
                        vector_store=vector_store,
                        reranker=reranker,
                    )
                elif tool_name == "lookup" and len(args) == 3:
                    observation = await _exec_lookup(
                        file_path=args[0],
                        start_line=int(args[1]),
                        end_line=int(args[2]),
                        project=body.project,
                        embedding_client=embedding_client,
                        vector_store=vector_store,
                    )
                else:
                    observation = f"未知工具或参数错误: {step.action}"
            except Exception as exc:
                logger.warning("Tool execution failed: %s", exc, exc_info=True)
                observation = f"工具执行出错: {exc}"

            # 截断
            max_obs_len = 4000
            if len(observation) > max_obs_len:
                observation = observation[:max_obs_len] + "\n...(结果已截断)"

            step.observation = observation
            steps.append(step)

            yield _sse({"type": "observation", "content": observation})
        else:
            # 超过 max_steps，强制生成最终答案
            messages = _build_agent_messages(body.question, steps, history)
            messages.append(
                {
                    "role": "user",
                    "content": "你已经进行了多步检索，请根据已收集到的所有信息，直接给出最终答案。不要再调用工具。",
                }
            )
            yield _sse({"type": "thought", "content": "已达到最大步数，正在综合已有信息生成答案..."})
            async for token in generate(messages, settings.vllm_url, settings.llm_model):
                yield _sse({"type": "token", "content": token})

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

        yield _sse({"type": "done", "session_id": session_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    """格式化 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
