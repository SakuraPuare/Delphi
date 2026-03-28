from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from qdrant_client.http.exceptions import UnexpectedResponse

from delphi.api.models import DebugSource, QueryDebugResponse, QueryRequest, QueryResponse, Source
from delphi.core.config import settings
from delphi.retrieval.intent import classify_intent
from delphi.retrieval.rag import build_prompt, generate, generate_sync, retrieve

logger = logging.getLogger(__name__)

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
        )
        for i, c in enumerate(chunks)
    ]


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request) -> QueryResponse:
    if not body.question.strip():
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
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            raise HTTPException(404, detail=f"项目 '{body.project}' 的集合不存在，请先导入数据") from exc
        raise

    session_id = session.session_id if session else None

    if not chunks:
        return QueryResponse(answer=NO_RESULTS_MSG, sources=[], session_id=session_id)

    messages = build_prompt(body.question, chunks, history=history)
    answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)

    if session:
        session.add_assistant_message(answer)

    return QueryResponse(answer=answer, sources=_chunks_to_sources(chunks), session_id=session_id)


@router.post("/query/stream")
async def query_stream(body: QueryRequest, request: Request):
    if not body.question.strip():
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
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            raise HTTPException(404, detail=f"项目 '{body.project}' 的集合不存在，请先导入数据") from exc
        raise

    if not chunks:

        async def empty_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': NO_RESULTS_MSG}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    messages = build_prompt(body.question, chunks, history=history)
    sources = [s.model_dump() for s in _chunks_to_sources(chunks)]

    async def event_stream():
        collected: list[str] = []
        async for token in generate(messages, settings.vllm_url, settings.llm_model):
            collected.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        # 记录完整回复到 session
        if session:
            session.add_assistant_message("".join(collected))
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
    if not body.question.strip():
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
    except UnexpectedResponse as exc:
        if exc.status_code == 404:
            raise HTTPException(404, detail=f"项目 '{body.project}' 的集合不存在，请先导入数据") from exc
        raise

    if not chunks:
        return QueryDebugResponse(
            answer=NO_RESULTS_MSG,
            timings=trace.timings or {},
            session_id=session_id,
        )

    messages = build_prompt(body.question, chunks, history=history)
    intent = classify_intent(body.question)

    t0 = time.monotonic()
    answer = await generate_sync(messages, settings.vllm_url, settings.llm_model)
    llm_ms = round((time.monotonic() - t0) * 1000, 2)

    if session:
        session.add_assistant_message(answer)

    timings = trace.timings or {}
    timings["llm_ms"] = llm_ms

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
