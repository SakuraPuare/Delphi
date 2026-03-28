from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from qdrant_client.http.exceptions import UnexpectedResponse

from delphi.api.models import DebugSource, QueryDebugResponse, QueryRequest, QueryResponse, Source
from delphi.core.config import settings
from delphi.retrieval.intent import classify_intent
from delphi.retrieval.rag import build_prompt, generate, generate_sync, retrieve

router = APIRouter(tags=["query"])

NO_RESULTS_MSG = "未找到相关内容，请尝试换一种提问方式。"


def _chunks_to_sources(chunks):
    return [
        Source(
            index=i + 1,
            file=c.file_path,
            chunk=c.content,
            score=c.score,
            start_line=c.start_line,
            end_line=c.end_line,
            repo_url=c.repo_url,
        )
        for i, c in enumerate(chunks)
    ]


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request) -> QueryResponse:
    logger.info(
        "收到查询请求, project={}, question={}, top_k={}, session_id={}",
        body.project,
        body.question[:80],
        body.top_k,
        body.session_id,
    )
    t_start = time.monotonic()

    if not body.question.strip():
        logger.warning("查询请求被拒绝: question 为空")
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
    sessions = request.app.state.sessions
    graph_store = request.app.state.graph_store

    # Session 管理
    session = None
    history = None
    if body.session_id:
        session = sessions.get(body.session_id)
        logger.debug("加载已有会话, session_id={}, found={}", body.session_id, session is not None)
    if session is None and body.session_id is None:
        session = sessions.create(body.project)
        logger.debug("创建新会话, session_id={}", session.session_id)

    if session:
        history = session.get_history()
        session.add_user_message(body.question)
        logger.debug("会话历史消息数: {}", len(history) if history else 0)

    try:
        chunks = await retrieve(
            question=body.question,
            project=body.project,
            top_k=body.top_k,
            embedding_client=embedding_client,
            vector_store=vector_store,
            reranker=reranker,
            use_graph_rag=body.use_graph_rag,
            graph_store=graph_store,
        )
        logger.debug("RAG 检索完成, 返回 {} 个结果", len(chunks))
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            logger.error("查询失败: 项目 '{}' 的集合不存在", body.project)
            raise HTTPException(404, detail=f"项目 '{body.project}' 的集合不存在，请先导入数据") from exc
        logger.exception("查询检索异常: {}", exc)
        raise

    session_id = session.session_id if session else None

    if not chunks:
        logger.info("查询无结果, project={}, question={}", body.project, body.question[:80])
        return QueryResponse(answer=NO_RESULTS_MSG, sources=[], session_id=session_id)

    messages = build_prompt(body.question, chunks, history=history)
    logger.debug("开始 LLM 生成, prompt 消息数: {}", len(messages))
    answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)

    if session:
        session.add_assistant_message(answer)

    elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
    logger.info("查询完成, project={}, 耗时={}ms, 来源数={}", body.project, elapsed_ms, len(chunks))
    return QueryResponse(answer=answer, sources=_chunks_to_sources(chunks), session_id=session_id)


@router.post("/query/stream")
async def query_stream(body: QueryRequest, request: Request):
    logger.info("收到流式查询请求, project={}, question={}, top_k={}", body.project, body.question[:80], body.top_k)

    if not body.question.strip():
        logger.warning("流式查询请求被拒绝: question 为空")
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
    sessions = request.app.state.sessions
    graph_store = request.app.state.graph_store

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

    try:
        chunks = await retrieve(
            question=body.question,
            project=body.project,
            top_k=body.top_k,
            embedding_client=embedding_client,
            vector_store=vector_store,
            reranker=reranker,
            use_graph_rag=body.use_graph_rag,
            graph_store=graph_store,
        )
        logger.debug("流式查询检索完成, 返回 {} 个结果", len(chunks))
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            logger.error("流式查询失败: 项目 '{}' 的集合不存在", body.project)
            raise HTTPException(404, detail=f"项目 '{body.project}' 的集合不存在，请先导入数据") from exc
        logger.exception("流式查询检索异常: {}", exc)
        raise

    if not chunks:
        logger.info("流式查询无结果, project={}", body.project)

        async def empty_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': NO_RESULTS_MSG}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    messages = build_prompt(body.question, chunks, history=history)
    sources = [s.model_dump() for s in _chunks_to_sources(chunks)]
    logger.debug("开始流式 LLM 生成, prompt 消息数: {}", len(messages))

    async def event_stream():
        collected: list[str] = []
        async for token in generate(messages, settings.vllm_url, settings.llm_model):
            collected.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        # 记录完整回复到 session
        if session:
            session.add_assistant_message("".join(collected))
        logger.debug("流式查询生成完成, token 数: {}", len(collected))
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _chunks_to_debug_sources(chunks, rerank_scores: bool = False) -> list[DebugSource]:
    return [
        DebugSource(
            file=c.file_path,
            chunk=c.content[:300],
            start_line=c.start_line,
            end_line=c.end_line,
            vector_score=c.vector_score,
            rerank_score=c.score if rerank_scores and c.score != c.vector_score else None,
            from_graph=c.from_graph,
            node_type=c.node_type,
            language=c.language,
        )
        for c in chunks
    ]


@router.post("/query/debug", response_model=QueryDebugResponse)
async def query_debug(body: QueryRequest, request: Request) -> QueryDebugResponse:
    """Run a query with full pipeline debug trace — returns intermediate results at each stage."""
    logger.info("收到调试查询请求, project={}, question={}", body.project, body.question[:80])
    t_start = time.monotonic()

    if not body.question.strip():
        logger.warning("调试查询请求被拒绝: question 为空")
        raise HTTPException(400, detail="question 不能为空")

    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker
    sessions = request.app.state.sessions
    graph_store = request.app.state.graph_store

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

    try:
        result = await retrieve(
            question=body.question,
            project=body.project,
            top_k=body.top_k,
            embedding_client=embedding_client,
            vector_store=vector_store,
            reranker=reranker,
            use_graph_rag=body.use_graph_rag,
            graph_store=graph_store,
            debug=True,
        )
        chunks, trace = result
        logger.debug(
            "调试查询检索完成, 向量结果={}, 重排结果={}, 最终结果={}",
            len(trace.vector_results or []),
            len(trace.reranked_results or []),
            len(trace.final_results or []),
        )
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            logger.error("调试查询失败: 项目 '{}' 的集合不存在", body.project)
            raise HTTPException(404, detail=f"项目 '{body.project}' 的集合不存在，请先导入数据") from exc
        logger.exception("调试查询检索异常: {}", exc)
        raise

    if not chunks:
        logger.info("调试查询无结果, project={}", body.project)
        return QueryDebugResponse(
            answer=NO_RESULTS_MSG,
            timings=trace.timings or {},
            session_id=session_id,
        )

    messages = build_prompt(body.question, chunks, history=history)
    intent = classify_intent(body.question)
    logger.debug("意图分类结果: intent={}", intent)

    t0 = time.monotonic()
    answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)
    llm_ms = round((time.monotonic() - t0) * 1000, 2)

    if session:
        session.add_assistant_message(answer)

    timings = trace.timings or {}
    timings["llm_ms"] = llm_ms

    elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
    logger.info("调试查询完成, project={}, 总耗时={}ms, LLM 耗时={}ms", body.project, elapsed_ms, llm_ms)

    return QueryDebugResponse(
        answer=answer,
        rewritten_query=trace.rewritten_query,
        intent=intent,
        vector_results=_chunks_to_debug_sources(trace.vector_results or []),
        reranked_results=_chunks_to_debug_sources(trace.reranked_results or [], rerank_scores=True),
        final_results=_chunks_to_debug_sources(trace.final_results or [], rerank_scores=True),
        timings=timings,
        session_id=session_id,
    )
