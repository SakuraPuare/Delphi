import logging

import httpx
from fastapi import APIRouter, Request

from delphi import __version__
from delphi.api.models import HealthResponse, ServiceStatus, StatusResponse
from delphi.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(version=__version__)


async def _check_service(url: str, paths: list[str] | None = None) -> ServiceStatus:
    """检查外部服务健康状态，依次尝试多个端点直到成功。"""
    if paths is None:
        paths = ["/health", "/"]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            for path in paths:
                try:
                    resp = await client.get(f"{url}{path}")
                    if resp.status_code < 400:
                        return ServiceStatus(ok=True, error=None)
                except httpx.RequestError:
                    continue
        return ServiceStatus(ok=False, error="all health endpoints failed")
    except Exception as e:
        return ServiceStatus(ok=False, error=str(e))


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    # Check Qdrant
    qdrant_ok = False
    try:
        qdrant_ok = await request.app.state.vector_store.healthy()
    except Exception as e:
        logger.warning("Qdrant health check failed: %s", e)

    # Check vLLM / OpenAI-compatible / Ollama LLM
    vllm_status = await _check_service(
        settings.vllm_url, ["/health", "/v1/models", "/api/tags", "/"]
    )
    # Check Embedding (TEI / Ollama / OpenAI-compatible)
    embedding_status = await _check_service(
        settings.embedding_url, ["/health", "/api/tags", "/"]
    )

    return StatusResponse(
        vllm=vllm_status,
        qdrant=ServiceStatus(ok=qdrant_ok, error=None if qdrant_ok else "unreachable"),
        embedding=embedding_status,
    )
