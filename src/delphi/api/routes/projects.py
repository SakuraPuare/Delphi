from fastapi import APIRouter, Request

from delphi.api.models import ProjectCreate, ProjectInfo

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectInfo])
async def list_projects(request: Request) -> list[ProjectInfo]:
    vs = request.app.state.vector_store
    try:
        collections = await vs._client.get_collections()
        return [ProjectInfo(name=c.name) for c in collections.collections]
    except Exception:
        # Qdrant not available, return empty
        return []


@router.post("", response_model=ProjectInfo, status_code=201)
async def create_project(body: ProjectCreate, request: Request) -> ProjectInfo:
    vs = request.app.state.vector_store
    await vs.ensure_collection(body.name)
    return ProjectInfo(name=body.name, description=body.description)


@router.delete("/{name}", status_code=204)
async def delete_project(name: str, request: Request) -> None:
    vs = request.app.state.vector_store
    if await vs.collection_exists(name):
        await vs.delete_collection(name)
