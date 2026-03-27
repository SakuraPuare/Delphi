from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from delphi import __version__
from delphi.api.routes import agent, finetune, graph, health, import_, models, openai_compat, projects, query, scheduler
from delphi.api.websocket import task_manager, ws_all_tasks, ws_single_task
from delphi.core.clients import EmbeddingClient, VectorStore
from delphi.core.config import settings
from delphi.core.telemetry import init_telemetry
from delphi.graph.store import GraphStore
from delphi.models.manager import ModelManager
from delphi.retrieval.rag import RerankerClient
from delphi.retrieval.session import SessionStore
from delphi.scheduler import SyncScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 OpenTelemetry（可选）
    if settings.otel_enabled:
        init_telemetry(service_name=settings.otel_service_name, otlp_endpoint=settings.otel_endpoint)
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    app.state.embedding = EmbeddingClient()
    app.state.vector_store = VectorStore()
    app.state.sessions = SessionStore()
    app.state.model_manager = ModelManager()
    app.state.graph_store = GraphStore()
    app.state.task_manager = task_manager
    if settings.reranker_enabled:
        app.state.reranker = RerankerClient()
    else:
        app.state.reranker = None

    # 启动定时同步调度器
    app.state.scheduler = SyncScheduler(
        embedding=app.state.embedding,
        vector_store=app.state.vector_store,
    )
    app.state.scheduler.start()

    yield

    # 停止调度器
    await app.state.scheduler.stop()
    await app.state.embedding.close()
    await app.state.vector_store.close()
    if app.state.reranker:
        await app.state.reranker.close()


app = FastAPI(
    title="Delphi",
    description="可离线部署的本地知识库系统",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(import_.router)
app.include_router(query.router)
app.include_router(agent.router)
app.include_router(models.router)
app.include_router(openai_compat.router)
app.include_router(finetune.router)
app.include_router(graph.router)
app.include_router(scheduler.router)


# ---- WebSocket 端点 ----


@app.websocket("/ws/tasks")
async def websocket_all_tasks(websocket: WebSocket) -> None:
    await ws_all_tasks(websocket)


@app.websocket("/ws/tasks/{task_id}")
async def websocket_single_task(websocket: WebSocket, task_id: str) -> None:
    await ws_single_task(websocket, task_id)
