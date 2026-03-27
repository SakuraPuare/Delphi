import logging

from fastapi import APIRouter, Request

from delphi import __version__
from delphi.api.models import HealthResponse, ServiceStatus, StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(version=__version__)


@router.get("/status", response_model=StatusResponse)
async def status(request: Request) -> StatusResponse:
    # Check Qdrant
    qdrant_ok = False
    try:
        qdrant_ok = await request.app.state.vector_store.healthy()
    except Exception as e:
        logger.warning("Qdrant health check failed: %s", e)

    # Embedding and vLLM checks are simple connectivity tests
    # TODO: implement actual health checks for embedding and vllm

    return StatusResponse(
        vllm=ServiceStatus(ok=False, error="health check not implemented"),
        qdrant=ServiceStatus(ok=qdrant_ok, error=None if qdrant_ok else "unreachable"),
        embedding=ServiceStatus(ok=False, error="health check not implemented"),
    )
