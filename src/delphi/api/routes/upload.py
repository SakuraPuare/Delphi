"""文件上传 API：分片上传 + 去重 + 触发导入"""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from delphi.api.models import (
    ChunkUploadResponse,
    TaskInfo,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitRequest,
    UploadInitResponse,
)
from delphi.core.cache import check_cache
from delphi.ingestion.doc_pipeline import run_doc_import
from delphi.ingestion.media_pipeline import run_media_import
from delphi.ingestion.pipeline import create_task
from delphi.ingestion.upload import (
    HashMismatchError,
    assemble,
    create_session,
    find_session_by_hash,
    load_session,
    save_chunk,
)

router = APIRouter(prefix="/import/upload", tags=["upload"])


@router.post("/init", response_model=UploadInitResponse)
async def upload_init(body: UploadInitRequest) -> UploadInitResponse:
    logger.info("收到上传初始化请求, file_name={}, file_hash={}, project={}", body.file_name, body.file_hash, body.project)

    if check_cache(body.project, body.file_hash):
        logger.info("文件已存在缓存中, file_hash={}", body.file_hash)
        return UploadInitResponse(status="exists")

    session = find_session_by_hash(body.file_hash)
    if session:
        logger.info("找到已有上传会话, upload_id={}, 已接收分片数={}", session.upload_id, len(session.received_chunks))
        return UploadInitResponse(
            status="partial",
            upload_id=session.upload_id,
            received_chunks=sorted(session.received_chunks),
        )

    upload_id = create_session(
        file_name=body.file_name,
        file_size=body.file_size,
        file_hash=body.file_hash,
        total_chunks=body.total_chunks,
        project=body.project,
        pipeline=body.pipeline,
    )
    logger.info("创建新上传会话, upload_id={}", upload_id)
    return UploadInitResponse(status="ready", upload_id=upload_id)


@router.put("/{upload_id}/chunks/{chunk_index}", response_model=ChunkUploadResponse)
async def upload_chunk(upload_id: str, chunk_index: int, request: Request) -> ChunkUploadResponse:
    logger.debug("收到分片上传请求, upload_id={}, chunk_index={}", upload_id, chunk_index)

    session = load_session(upload_id)
    if session is None:
        logger.warning("上传会话不存在, upload_id={}", upload_id)
        raise HTTPException(404, detail=f"上传会话 '{upload_id}' 不存在")

    if not (0 <= chunk_index < session.total_chunks):
        logger.warning("分片索引无效, chunk_index={}, total_chunks={}", chunk_index, session.total_chunks)
        raise HTTPException(400, detail=f"分片索引无效: {chunk_index}, 有效范围 [0, {session.total_chunks})")

    data = await request.body()
    save_chunk(upload_id, chunk_index, data)
    logger.debug("分片已保存, upload_id={}, chunk_index={}", upload_id, chunk_index)
    return ChunkUploadResponse(chunk_index=chunk_index, received=True)


@router.post("/{upload_id}/complete", response_model=UploadCompleteResponse, status_code=202)
async def upload_complete(upload_id: str, body: UploadCompleteRequest, request: Request) -> UploadCompleteResponse:
    logger.info("收到上传完成请求, upload_id={}, trigger_pipeline={}", upload_id, body.trigger_pipeline)

    session = load_session(upload_id)
    if session is None:
        logger.warning("上传会话不存在, upload_id={}", upload_id)
        raise HTTPException(404, detail=f"上传会话 '{upload_id}' 不存在")

    if len(session.received_chunks) != session.total_chunks:
        missing = sorted(set(range(session.total_chunks)) - set(session.received_chunks))
        logger.warning("分片不完整, upload_id={}, 缺失分片={}", upload_id, missing)
        raise HTTPException(400, detail=f"分片不完整, 缺失: {missing}")

    try:
        final_path = assemble(upload_id)
    except HashMismatchError:
        logger.error("文件哈希不匹配, upload_id={}", upload_id)
        return UploadCompleteResponse(status="hash_mismatch")

    task_id: str | None = None

    if body.trigger_pipeline:
        from delphi.core.cache import get_upload_dir

        upload_dir = str(get_upload_dir(session.project))

        if session.pipeline == "doc":
            params = {"path": upload_dir, "project": session.project}
            task_id = create_task(task_type="doc_import", params=params)
            asyncio.create_task(
                run_doc_import(
                    task_id=task_id,
                    path=upload_dir,
                    project=session.project,
                    embedding=request.app.state.embedding,
                    vector_store=request.app.state.vector_store,
                )
            )
            logger.info("文档导入任务已创建, task_id={}", task_id)
        elif session.pipeline == "media":
            params = {"path": upload_dir, "project": session.project}
            task_id = create_task(task_type="media_import", params=params)
            asyncio.create_task(
                run_media_import(
                    task_id=task_id,
                    path=upload_dir,
                    project=session.project,
                    embedding=request.app.state.embedding,
                    vector_store=request.app.state.vector_store,
                )
            )
            logger.info("媒体导入任务已创建, task_id={}", task_id)

    logger.info("上传完成, upload_id={}, file_path={}, task_id={}", upload_id, final_path, task_id)
    return UploadCompleteResponse(status="ok", file_path=str(final_path), task_id=task_id)
