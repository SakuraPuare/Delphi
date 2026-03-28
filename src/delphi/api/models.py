from typing import Literal

from pydantic import BaseModel

# --- Health ---


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class ServiceStatus(BaseModel):
    ok: bool
    model: str | None = None
    collections: int | None = None
    error: str | None = None


class StatusResponse(BaseModel):
    vllm: ServiceStatus
    qdrant: ServiceStatus
    embedding: ServiceStatus


# --- Projects ---


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectInfo(BaseModel):
    name: str
    description: str = ""
    chunk_count: int = 0
    created_at: str = ""


# --- Import ---


class GitImportRequest(BaseModel):
    url: str
    project: str
    branch: str = "main"
    include: list[str] = []
    exclude: list[str] = []
    depth: int = 1


class DocImportRequest(BaseModel):
    path: str
    project: str
    recursive: bool = True
    file_types: list[str] = ["md", "txt", "pdf", "html"]


class MediaImportRequest(BaseModel):
    path: str
    project: str
    recursive: bool = True
    whisper_model: str = "large-v3"


class TaskInfo(BaseModel):
    task_id: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    progress: float = 0.0
    total: int = 0
    processed: int = 0
    error: str | None = None


# --- Query ---


class QueryRequest(BaseModel):
    question: str
    project: str = ""
    top_k: int = 5
    session_id: str | None = None  # 传入 session_id 启用多轮对话
    use_graph_rag: bool = True  # 是否启用 Graph RAG 图谱扩展


class Source(BaseModel):
    index: int = 0
    file: str
    chunk: str = ""
    score: float = 0.0
    start_line: int | None = None
    end_line: int | None = None
    repo_url: str = ""


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = []
    session_id: str | None = None  # 返回 session_id 供后续使用


# --- Agent ---


class AgentQueryRequest(BaseModel):
    question: str
    project: str = ""
    max_steps: int = 5
    session_id: str | None = None


class AgentStepModel(BaseModel):
    thought: str
    action: str | None = None
    observation: str | None = None
    answer: str | None = None


class AgentQueryResponse(BaseModel):
    answer: str
    steps: list[AgentStepModel] = []
    sources: list[Source] = []
    session_id: str | None = None


# --- Finetune ---


class FinetuneGenRequest(BaseModel):
    project: str
    num_samples: int = 100
    questions_per_chunk: int = 2
    format: str = "jsonl"  # jsonl | alpaca | sharegpt
    output_path: str = ""  # 空则返回内容


# --- Models ---


class ModelRegisterRequest(BaseModel):
    name: str
    model_path: str
    model_type: str = "base"  # base | lora
    base_model: str = ""
    description: str = ""


class ModelInfoResponse(BaseModel):
    name: str
    model_path: str
    model_type: str = "base"
    base_model: str = ""
    description: str = ""
    active: bool = False


class ModelActivateRequest(BaseModel):
    name: str


# --- Error ---


class ErrorResponse(BaseModel):
    code: str
    message: str


# --- Graph ---


class GraphBuildRequest(BaseModel):
    project: str
    path: str  # 代码目录路径
    include: list[str] = []
    exclude: list[str] = []


class SymbolInfo(BaseModel):
    name: str
    qualified_name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    language: str


class RelationInfo(BaseModel):
    source: str
    target: str
    kind: str


class GraphQueryResponse(BaseModel):
    symbols: list[SymbolInfo] = []
    relations: list[RelationInfo] = []


# --- Pipeline Debug ---


class ChunkDetail(BaseModel):
    id: str
    text_preview: str
    file_path: str
    language: str = ""
    node_type: str = ""
    symbol_name: str = ""
    parent_symbol: str = ""
    start_line: int = 0
    end_line: int = 0


class ChunkListResponse(BaseModel):
    chunks: list[ChunkDetail]
    next_offset: str | None = None
    total: int = 0


class ProjectStats(BaseModel):
    total_chunks: int = 0
    by_language: dict[str, int] = {}
    by_node_type: dict[str, int] = {}
    top_files: list[dict[str, int | str]] = []


class DebugSource(BaseModel):
    file: str
    chunk: str = ""
    start_line: int | None = None
    end_line: int | None = None
    vector_score: float = 0.0
    rerank_score: float | None = None
    from_graph: bool = False
    node_type: str = ""
    language: str = ""


class QueryDebugResponse(BaseModel):
    answer: str
    rewritten_query: str | None = None
    intent: str = ""
    vector_results: list[DebugSource] = []
    reranked_results: list[DebugSource] = []
    final_results: list[DebugSource] = []
    timings: dict[str, float] = {}
    session_id: str | None = None
