from fastapi import APIRouter, HTTPException

from delphi.api.models import ProjectCreate, ProjectInfo

router = APIRouter(prefix="/projects", tags=["projects"])

# TODO: 替换为真实的 Qdrant 集合管理
_projects: dict[str, ProjectInfo] = {}


@router.get("", response_model=list[ProjectInfo])
async def list_projects() -> list[ProjectInfo]:
    return list(_projects.values())


@router.post("", response_model=ProjectInfo, status_code=201)
async def create_project(body: ProjectCreate) -> ProjectInfo:
    if body.name in _projects:
        raise HTTPException(400, detail=f"项目 '{body.name}' 已存在")
    info = ProjectInfo(name=body.name, description=body.description)
    _projects[body.name] = info
    return info


@router.delete("/{name}", status_code=204)
async def delete_project(name: str) -> None:
    if name not in _projects:
        raise HTTPException(404, detail=f"项目 '{name}' 不存在")
    del _projects[name]
