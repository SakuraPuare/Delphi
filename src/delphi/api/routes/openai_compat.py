"""OpenAI 兼容 API：让第三方客户端通过 /v1 路由访问 Delphi。"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from delphi.core.config import settings
from delphi.retrieval.rag import build_prompt, generate, generate_sync, retrieve

router = APIRouter(prefix="/v1", tags=["openai-compat"])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "delphi"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _make_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _ts() -> int:
    return int(time.time())


def _extract_question(messages: list[ChatMessage]) -> str:
    """从 messages 中提取最后一条 user 消息作为检索 query。"""
    for msg in reversed(messages):
        if msg.role == "user" and msg.content.strip():
            return msg.content.strip()
    return ""


def _build_plain_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """将 ChatMessage 列表转为 vLLM 可用的 dict 列表（无 RAG 上下文）。"""
    return [{"role": m.role, "content": m.content} for m in messages]


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(request: Request) -> dict[str, Any]:
    logger.debug("收到 OpenAI 兼容模型列表请求")
    mgr = request.app.state.model_manager
    registered = mgr.list_models()

    data = [
        {
            "id": "delphi",
            "object": "model",
            "created": _ts(),
            "owned_by": "delphi",
        }
    ]
    for m in registered:
        data.append(
            {
                "id": m.name,
                "object": "model",
                "created": _ts(),
                "owned_by": "delphi",
            }
        )

    logger.debug("返回 OpenAI 兼容模型列表, 模型数={}", len(data))
    return {"object": "list", "data": data}


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------


@router.post("/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    logger.info(
        "收到 OpenAI 兼容聊天请求, model={}, stream={}, messages_count={}", body.model, body.stream, len(body.messages)
    )
    question = _extract_question(body.messages)
    logger.debug("提取用户问题: {}", question[:80] if question else "(空)")

    # 从 app.state 获取 RAG 依赖
    embedding_client = request.app.state.embedding
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker

    # RAG 检索（project 为空 = 搜索所有 collection）
    chunks = []
    if question:
        try:
            chunks = await retrieve(
                question=question,
                project="",
                top_k=settings.chunk_top_k,
                embedding_client=embedding_client,
                vector_store=vector_store,
                reranker=reranker,
            )
            logger.debug("OpenAI 兼容 RAG 检索完成, 返回 {} 个结果", len(chunks))
        except Exception:
            logger.warning("RAG 检索失败, 回退到直接对话", exc_info=True)

    # 构建 prompt：有检索结果用 RAG prompt，否则直接转发用户消息
    prompt_messages = build_prompt(question, chunks) if chunks else _build_plain_messages(body.messages)

    completion_id = _make_id()

    if body.stream:
        logger.debug("开始流式响应, completion_id={}", completion_id)
        return StreamingResponse(
            _stream_response(completion_id, prompt_messages),
            media_type="text/event-stream",
        )

    # 非流式
    logger.debug("开始非流式响应, completion_id={}", completion_id)
    answer = await generate_sync(prompt_messages, settings.vllm_url, settings.llm_model)
    logger.info("OpenAI 兼容聊天完成, completion_id={}, answer_len={}", completion_id, len(answer))
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": _ts(),
        "model": "delphi",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_response(completion_id: str, messages: list[dict]):
    """生成 SSE 流式响应，格式与 OpenAI API 一致。"""
    logger.debug("开始 OpenAI 兼容流式生成, completion_id={}", completion_id)

    def _chunk(content: str | None, finish_reason: str | None = None) -> str:
        delta: dict[str, str] = {}
        if content is not None:
            delta["content"] = content
        obj = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": _ts(),
            "model": "delphi",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    # 首个 chunk 带 role
    first_obj = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": _ts(),
        "model": "delphi",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(first_obj, ensure_ascii=False)}\n\n"

    async for token in generate(messages, settings.vllm_url, settings.llm_model):
        yield _chunk(token)

    # 结束标记
    yield _chunk(None, finish_reason="stop")
    yield "data: [DONE]\n\n"
