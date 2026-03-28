from collections import Counter

from fastapi import APIRouter, Request

from delphi.api.models import ChunkDetail, ChunkListResponse, ProjectCreate, ProjectInfo, ProjectStats

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectInfo])
async def list_projects(request: Request) -> list[ProjectInfo]:
    vs = request.app.state.vector_store
    try:
        collections = await vs._client.get_collections()
        result = []
        for c in collections.collections:
            count = await vs.count(c.name)
            result.append(ProjectInfo(name=c.name, chunk_count=count))
        return result
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

    return ChunkListResponse(chunks=chunks, next_offset=str(next_off) if next_off else None, total=total)


@router.get("/{name}/stats", response_model=ProjectStats)
async def project_stats(name: str, request: Request) -> ProjectStats:
    vs = request.app.state.vector_store
    total = await vs.count(name)

    # Scroll all points to aggregate stats (for collections up to ~100k)
    lang_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    file_counter: Counter[str] = Counter()

    offset = None
    while True:
        records, offset = await vs.scroll(name, limit=100, offset=offset)
        for r in records:
            p = r.payload or {}
            lang_counter[p.get("language", "unknown")] += 1
            type_counter[p.get("node_type", "unknown")] += 1
            file_counter[p.get("file_path", "unknown")] += 1
        if offset is None:
            break

    top_files = [{"file_path": f, "count": c} for f, c in file_counter.most_common(20)]

    return ProjectStats(
        total_chunks=total,
        by_language=dict(lang_counter),
        by_node_type=dict(type_counter),
        top_files=top_files,
    )
