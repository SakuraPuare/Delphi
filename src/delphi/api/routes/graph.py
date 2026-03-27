"""代码图谱 API 路由"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from delphi.api.models import (
    GraphBuildRequest,
    GraphQueryResponse,
    RelationInfo,
    SymbolInfo,
    TaskInfo,
)
from delphi.graph.extractor import extract_from_directory
from delphi.ingestion.pipeline import create_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


async def _build_graph(task_id: str, request: Request, body: GraphBuildRequest) -> None:
    """后台构建代码图谱"""
    from pathlib import Path

    from delphi.ingestion.pipeline import _tasks

    task = _tasks[task_id]
    task["status"] = "running"

    try:
        root = Path(body.path)
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {body.path}")

        graph = await asyncio.to_thread(
            extract_from_directory,
            root,
            include=body.include or None,
            exclude=body.exclude or None,
        )

        store = request.app.state.graph_store
        store.save(body.project, graph)

        task["total"] = len(graph.symbols)
        task["processed"] = len(graph.symbols)
        task["progress"] = 1.0
        task["status"] = "done"

    except Exception as e:
        logger.error("Graph build failed: %s", e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)


@router.post("/build", response_model=TaskInfo, status_code=202)
async def build_graph(body: GraphBuildRequest, request: Request) -> TaskInfo:
    """构建代码图谱（后台任务）"""
    task_id = create_task()
    asyncio.create_task(_build_graph(task_id, request, body))
    return TaskInfo(task_id=task_id, status="pending")


@router.get("/{project}", response_model=GraphQueryResponse)
async def get_graph(project: str, request: Request) -> GraphQueryResponse:
    """获取完整图谱"""
    store = request.app.state.graph_store
    graph = store.get(project)
    if graph is None:
        raise HTTPException(404, detail=f"图谱 '{project}' 不存在")
    return GraphQueryResponse(
        symbols=[SymbolInfo(**s.__dict__) for s in graph.symbols.values()],
        relations=[RelationInfo(**r.__dict__) for r in graph.relations],
    )


@router.get("/{project}/symbol/{name:path}", response_model=GraphQueryResponse)
async def query_symbol(project: str, name: str, request: Request) -> GraphQueryResponse:
    """查询符号的调用关系"""
    store = request.app.state.graph_store
    graph = store.get(project)
    if graph is None:
        raise HTTPException(404, detail=f"图谱 '{project}' 不存在")

    # 查找匹配的符号（支持部分匹配）
    matched_symbols = [s for s in graph.symbols.values() if name in s.qualified_name or name == s.name]
    if not matched_symbols:
        raise HTTPException(404, detail=f"符号 '{name}' 未找到")

    # 收集相关关系
    qnames = {s.qualified_name for s in matched_symbols}
    related = [r for r in graph.relations if r.source in qnames or r.target in qnames]
    return GraphQueryResponse(
        symbols=[SymbolInfo(**s.__dict__) for s in matched_symbols],
        relations=[RelationInfo(**r.__dict__) for r in related],
    )


@router.get("/{project}/file/{path:path}", response_model=GraphQueryResponse)
async def query_file(project: str, path: str, request: Request) -> GraphQueryResponse:
    """查询文件的依赖关系"""
    store = request.app.state.graph_store
    graph = store.get(project)
    if graph is None:
        raise HTTPException(404, detail=f"图谱 '{project}' 不存在")

    file_symbols = [s for s in graph.symbols.values() if s.file_path == path]
    file_relations = [r for r in graph.relations if r.source.startswith(path) or r.target.startswith(path)]
    return GraphQueryResponse(
        symbols=[SymbolInfo(**s.__dict__) for s in file_symbols],
        relations=[RelationInfo(**r.__dict__) for r in file_relations],
    )
