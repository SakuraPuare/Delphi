from fastapi import APIRouter, HTTPException

from delphi.api.models import DocImportRequest, GitImportRequest, TaskInfo

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/git", response_model=TaskInfo, status_code=202)
async def import_git(body: GitImportRequest) -> TaskInfo:
    # TODO: 启动异步导入任务
    raise HTTPException(501, detail="Git 导入尚未实现")


@router.post("/docs", response_model=TaskInfo, status_code=202)
async def import_docs(body: DocImportRequest) -> TaskInfo:
    # TODO: 启动异步导入任务
    raise HTTPException(501, detail="文档导入尚未实现")


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str) -> TaskInfo:
    # TODO: 查询任务状态
    raise HTTPException(501, detail="任务查询尚未实现")
