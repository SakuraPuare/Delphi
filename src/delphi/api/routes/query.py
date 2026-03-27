from fastapi import APIRouter, HTTPException

from delphi.api.models import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest) -> QueryResponse:
    # TODO: 实现 RAG pipeline
    raise HTTPException(501, detail="查询功能尚未实现")


@router.post("/query/stream")
async def query_stream(body: QueryRequest):
    # TODO: 实现 SSE 流式输出
    raise HTTPException(501, detail="流式查询尚未实现")
