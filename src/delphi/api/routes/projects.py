from collections import Counter

from fastapi import APIRouter, Request
from loguru import logger

from delphi.api.models import ChunkDetail, ChunkListResponse, ProjectCreate, ProjectInfo, ProjectStats

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectInfo])
async def list_projects(request: Request) -> list[ProjectInfo]:
    logger.info("收到列出项目请求")
    vs = request.app.state.vector_store
    try:
        collections = await vs._client.get_collections()
        result = []
        for c in collections.collections:
            count = await vs.count(c.name)
            result.append(ProjectInfo(name=c.name, chunk_count=count))
        logger.debug("返回项目列表, 项目数={}", len(result))
        return result
    except Exception as e:
        # Qdrant not available, return empty
        logger.warning("获取项目列表失败 (Qdrant 不可用): {}", e)
        return []


@router.post("", response_model=ProjectInfo, status_code=201)
async def create_project(body: ProjectCreate, request: Request) -> ProjectInfo:
    logger.info(
        "收到创建项目请求, name={}, description={}", body.name, body.description[:50] if body.description else ""
    )
    vs = request.app.state.vector_store
    await vs.ensure_collection(body.name)
    logger.info("项目创建成功, name={}", body.name)
    return ProjectInfo(name=body.name, description=body.description)


@router.delete("/{name}", status_code=204)
async def delete_project(name: str, request: Request) -> None:
    logger.info("收到删除项目请求, name={}", name)
    vs = request.app.state.vector_store
    if await vs.collection_exists(name):
        await vs.delete_collection(name)
        logger.info("项目已删除, name={}", name)
    else:
        logger.debug("项目不存在, 跳过删除, name={}", name)


@router.get("/{name}/chunks", response_model=ChunkListResponse)
async def list_chunks(
    name: str,
    request: Request,
    limit: int = 50,
    offset: str | None = None,
    language: str | None = None,
    node_type: str | None = None,
    file_path: str | None = None,
) -> ChunkListResponse:
    logger.debug(
        "收到列出 chunks 请求, project={}, limit={}, offset={}, language={}, node_type={}, file_path={}",
        name,
        limit,
        offset,
        language,
        node_type,
        file_path,
    )
    vs = request.app.state.vector_store
    filters: dict[str, str] = {}
    if language:
        filters["language"] = language
    if node_type:
        filters["node_type"] = node_type
    if file_path:
        filters["file_path"] = file_path

    records, next_off = await vs.scroll(name, limit=min(limit, 100), offset=offset, filters=filters or None)
    total = await vs.count(name)

    chunks = []
    for r in records:
        p = r.payload or {}
        chunks.append(
            ChunkDetail(
                id=str(r.id),
                text_preview=p.get("text", "")[:200],
                file_path=p.get("file_path", ""),
                language=p.get("language", ""),
                node_type=p.get("node_type", ""),
                symbol_name=p.get("symbol_name", ""),
                parent_symbol=p.get("parent_symbol", ""),
                start_line=p.get("start_line", 0),
                end_line=p.get("end_line", 0),
            )
        )

    logger.debug("返回 chunks, project={}, 返回数={}, 总数={}", name, len(chunks), total)
    return ChunkListResponse(chunks=chunks, next_offset=str(next_off) if next_off else None, total=total)


@router.get("/{name}/stats", response_model=ProjectStats)
async def project_stats(name: str, request: Request) -> ProjectStats:
    logger.info("收到项目统计请求, project={}", name)
    vs = request.app.state.vector_store
    total = await vs.count(name)

    # Scroll all points to aggregate stats (for collections up to ~100k)
    lang_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    file_counter: Counter[str] = Counter()

    offset = None
    batch_count = 0
    while True:
        records, offset = await vs.scroll(name, limit=100, offset=offset)
        batch_count += 1
        for r in records:
            p = r.payload or {}
            lang_counter[p.get("language", "unknown")] += 1
            type_counter[p.get("node_type", "unknown")] += 1
            file_counter[p.get("file_path", "unknown")] += 1
        if offset is None:
            break

    top_files = [{"file_path": f, "count": c} for f, c in file_counter.most_common(20)]
    logger.info(
        "项目统计完成, project={}, total_chunks={}, 语言种类={}, 节点类型数={}, 滚动批次={}",
        name,
        total,
        len(lang_counter),
        len(type_counter),
        batch_count,
    )

    return ProjectStats(
        total_chunks=total,
        by_language=dict(lang_counter),
        by_node_type=dict(type_counter),
        top_files=top_files,
    )
