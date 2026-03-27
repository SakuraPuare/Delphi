from fastapi import APIRouter

from delphi import __version__
from delphi.api.models import HealthResponse, ServiceStatus, StatusResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(version=__version__)


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    # TODO: 实际检查各服务连通性
    return StatusResponse(
        vllm=ServiceStatus(ok=False, error="not implemented"),
        qdrant=ServiceStatus(ok=False, error="not implemented"),
        embedding=ServiceStatus(ok=False, error="not implemented"),
    )
