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


async def _check_service(url: str, path: str = "/health") -> ServiceStatus:
    """检查外部服务健康状态，若端点返回 404 则回退到根路径。"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{url}{path}")
            if resp.status_code == 404 and path != "/":
                resp = await client.get(f"{url}/")
            resp.raise_for_status()
        return ServiceStatus(ok=True, error=None)
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

    # Check vLLM and Embedding
    vllm_status = await _check_service(settings.vllm_url)
    embedding_status = await _check_service(settings.embedding_url)

    return StatusResponse(
        vllm=vllm_status,
        qdrant=ServiceStatus(ok=qdrant_ok, error=None if qdrant_ok else "unreachable"),
        embedding=embedding_status,
    )
