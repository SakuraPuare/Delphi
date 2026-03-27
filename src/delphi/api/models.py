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


class TaskInfo(BaseModel):
    task_id: str
    status: str = "pending"
    progress: float = 0.0
    total: int = 0
    processed: int = 0
    error: str | None = None


# --- Query ---


class QueryRequest(BaseModel):
    question: str
    project: str = ""
    top_k: int = 5


class Source(BaseModel):
    file: str
    chunk: str = ""
    score: float = 0.0


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source] = []


# --- Error ---


class ErrorResponse(BaseModel):
    code: str
    message: str
