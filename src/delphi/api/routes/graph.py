"""代码图谱 API 路由"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from delphi.api.models import (
    GraphBuildRequest,
    GraphQueryResponse,
    RelationInfo,
    SymbolInfo,
    TaskInfo,
)
from delphi.api.websocket import task_manager
from delphi.graph.extractor import extract_from_directory
from delphi.ingestion.pipeline import create_task

router = APIRouter(prefix="/graph", tags=["graph"])


async def _build_graph(task_id: str, request: Request, body: GraphBuildRequest) -> None:
    """后台构建代码图谱"""
    from pathlib import Path

    from delphi.ingestion.pipeline import _tasks

    task = _tasks[task_id]
    task["status"] = "running"
    task_manager.update_progress(task_id, 0, "开始构建代码图谱")
    logger.info("开始构建代码图谱, task_id={}, project={}, path={}", task_id, body.project, body.path)

    try:
        root = Path(body.path)
        if not root.exists():
            logger.error("图谱构建失败: 路径不存在, path={}", body.path)
            raise FileNotFoundError(f"路径不存在: {body.path}")

        task_manager.update_progress(task_id, 10, "提取代码符号中")
        logger.debug("开始提取代码符号, path={}, include={}, exclude={}", body.path, body.include, body.exclude)

        t_start = time.monotonic()
        graph = await asyncio.to_thread(
            extract_from_directory,
            root,
            include=body.include or None,
            exclude=body.exclude or None,
        )
        extract_ms = round((time.monotonic() - t_start) * 1000, 2)
        logger.debug(
            "代码符号提取完成, 符号数={}, 关系数={}, 耗时={}ms", len(graph.symbols), len(graph.relations), extract_ms
        )

        task_manager.update_progress(task_id, 80, "保存图谱数据")

        store = request.app.state.graph_store
        store.save(body.project, graph)

        task["total"] = len(graph.symbols)
        task["processed"] = len(graph.symbols)
        task["progress"] = 1.0
        task["status"] = "done"
        task_manager.complete_task(task_id, {"symbols": len(graph.symbols)})
        logger.info("图谱构建完成, task_id={}, project={}, 符号数={}", task_id, body.project, len(graph.symbols))

    except Exception as e:
        logger.error("图谱构建失败, task_id={}, error={}", task_id, e, exc_info=True)
        task["status"] = "failed"
        task["error"] = str(e)
        task_manager.fail_task(task_id, str(e))


@router.post("/build", response_model=TaskInfo, status_code=202)
async def build_graph(body: GraphBuildRequest, request: Request) -> TaskInfo:
    """构建代码图谱（后台任务）"""
    logger.info("收到图谱构建请求, project={}, path={}", body.project, body.path)
    task_id = create_task(task_type="graph_build")
    asyncio.create_task(_build_graph(task_id, request, body))
    logger.debug("图谱构建任务已创建, task_id={}", task_id)
    return TaskInfo(task_id=task_id, status="pending")


@router.get("/{project}", response_model=GraphQueryResponse)
async def get_graph(project: str, request: Request) -> GraphQueryResponse:
    """获取完整图谱"""
    logger.info("收到获取图谱请求, project={}", project)
    store = request.app.state.graph_store
    graph = store.get(project)
    if graph is None:
        logger.warning("图谱不存在, project={}", project)
        raise HTTPException(404, detail=f"图谱 '{project}' 不存在")
    logger.debug("返回图谱数据, project={}, 符号数={}, 关系数={}", project, len(graph.symbols), len(graph.relations))
    return GraphQueryResponse(
        symbols=[SymbolInfo(**s.__dict__) for s in graph.symbols.values()],
        relations=[RelationInfo(**r.__dict__) for r in graph.relations],
    )


@router.get("/{project}/symbol/{name:path}", response_model=GraphQueryResponse)
async def query_symbol(project: str, name: str, request: Request) -> GraphQueryResponse:
    """查询符号的调用关系"""
    logger.info("收到符号查询请求, project={}, symbol={}", project, name)
    store = request.app.state.graph_store
    graph = store.get(project)
    if graph is None:
        logger.warning("图谱不存在, project={}", project)
        raise HTTPException(404, detail=f"图谱 '{project}' 不存在")

    # 查找匹配的符号（支持部分匹配）
    matched_symbols = [s for s in graph.symbols.values() if name in s.qualified_name or name == s.name]
    if not matched_symbols:
        logger.warning("符号未找到, project={}, symbol={}", project, name)
        raise HTTPException(404, detail=f"符号 '{name}' 未找到")

    # 收集相关关系
    qnames = {s.qualified_name for s in matched_symbols}
    related = [r for r in graph.relations if r.source in qnames or r.target in qnames]
    logger.debug("符号查询完成, 匹配符号数={}, 相关关系数={}", len(matched_symbols), len(related))
    return GraphQueryResponse(
        symbols=[SymbolInfo(**s.__dict__) for s in matched_symbols],
        relations=[RelationInfo(**r.__dict__) for r in related],
    )


@router.get("/{project}/file/{path:path}", response_model=GraphQueryResponse)
async def query_file(project: str, path: str, request: Request) -> GraphQueryResponse:
    """查询文件的依赖关系"""
    logger.info("收到文件依赖查询请求, project={}, path={}", project, path)
    store = request.app.state.graph_store
    graph = store.get(project)
    if graph is None:
        logger.warning("图谱不存在, project={}", project)
        raise HTTPException(404, detail=f"图谱 '{project}' 不存在")

    file_symbols = [s for s in graph.symbols.values() if s.file_path == path]
    file_relations = [r for r in graph.relations if r.source.startswith(path) or r.target.startswith(path)]
    logger.debug("文件依赖查询完成, 符号数={}, 关系数={}", len(file_symbols), len(file_relations))
    return GraphQueryResponse(
        symbols=[SymbolInfo(**s.__dict__) for s in file_symbols],
        relations=[RelationInfo(**r.__dict__) for r in file_relations],
    )
