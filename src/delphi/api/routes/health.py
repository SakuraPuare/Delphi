import time

import httpx
from fastapi import APIRouter, Request
from loguru import logger

from delphi import __version__
from delphi.api.models import HealthResponse, ServiceStatus, StatusResponse
from delphi.core.config import settings

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    logger.debug("收到健康检查请求")
    return HealthResponse(version=__version__)


async def _check_service(url: str, paths: list[str] | None = None, api_key: str | None = None) -> ServiceStatus:
    """检查外部服务健康状态，依次尝试多个端点直到成功。"""
    if paths is None:
        paths = ["/health", "/"]
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            for path in paths:
                try:
                    resp = await client.get(f"{url}{path}", headers=headers)
                    if resp.status_code < 400:
                        logger.debug("服务健康检查通过, url={}{}", url, path)
                        return ServiceStatus(ok=True, error=None)
                except httpx.RequestError:
                    logger.debug("服务端点不可达, url={}{}", url, path)
                    continue
        logger.warning("服务所有健康端点均失败, url={}", url)
        return ServiceStatus(ok=False, error="all health endpoints failed")
    except Exception as e:
        logger.error("服务健康检查异常, url={}, error={}", url, e)
        return ServiceStatus(ok=False, error=str(e))


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    logger.info("收到系统状态检查请求")
    t_start = time.monotonic()

    # Check Qdrant
    qdrant_ok = False
    try:
        qdrant_ok = await request.app.state.vector_store.healthy()
        logger.debug("Qdrant 健康检查结果: ok={}", qdrant_ok)
    except Exception as e:
        logger.warning("Qdrant 健康检查失败: {}", e)

    # Check vLLM / OpenAI-compatible / Ollama LLM
    vllm_status = await _check_service(
        settings.vllm_url, ["/health", "/v1/models", "/api/tags", "/"],
        api_key=settings.llm_api_key,
    )
    # Check Embedding (TEI / Ollama / OpenAI-compatible)
    embedding_status = await _check_service(settings.embedding_url, ["/health", "/api/tags", "/"])

    elapsed_ms = round((time.monotonic() - t_start) * 1000, 2)
    logger.info(
        "系统状态检查完成, 耗时={}ms, vllm={}, qdrant={}, embedding={}",
        elapsed_ms,
        vllm_status.ok,
        qdrant_ok,
        embedding_status.ok,
    )

    return StatusResponse(
        vllm=vllm_status,
        qdrant=ServiceStatus(ok=qdrant_ok, error=None if qdrant_ok else "unreachable"),
        embedding=embedding_status,
    )
