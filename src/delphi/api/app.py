from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from delphi import __version__
from delphi.api.routes import agent, finetune, graph, health, import_, models, openai_compat, projects, query, scheduler
from delphi.api.routes import eval as eval_routes
from delphi.api.routes import settings as settings_routes
from delphi.api.websocket import task_manager, ws_all_tasks, ws_single_task
from delphi.core.clients import EmbeddingClient, VectorStore
from delphi.core.config import settings
from delphi.core.logging import setup_logging
from delphi.core.task_store import TaskStore
from delphi.core.telemetry import init_telemetry
from delphi.graph.store import GraphStore
from delphi.models.manager import ModelManager
from delphi.retrieval.rag import RerankerClient
from delphi.retrieval.session import SessionStore
from delphi.scheduler import SyncScheduler

# 在模块加载时初始化日志系统
setup_logging(level="DEBUG" if settings.debug else "INFO")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Delphi v{} 启动中...", __version__)

    # 初始化 OpenTelemetry（可选）
    if settings.otel_enabled:
        init_telemetry(service_name=settings.otel_service_name, otlp_endpoint=settings.otel_endpoint)
        logger.info("OpenTelemetry 已启用, endpoint={}", settings.otel_endpoint)
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
            logger.debug("FastAPI OTel instrumentation 已挂载")
        except ImportError:
            logger.warning("opentelemetry-instrumentation-fastapi 未安装，跳过 FastAPI instrumentation")

    logger.debug("初始化 EmbeddingClient...")
    app.state.embedding = EmbeddingClient()
    logger.debug("初始化 VectorStore...")
    app.state.vector_store = VectorStore()
    app.state.sessions = SessionStore()
    app.state.model_manager = ModelManager()
    logger.debug("初始化 GraphStore...")
    app.state.graph_store = GraphStore()
    app.state.task_manager = task_manager
    if settings.reranker_enabled:
        logger.debug("初始化 RerankerClient...")
        app.state.reranker = RerankerClient()
    else:
        logger.info("Reranker 未启用，跳过初始化")
        app.state.reranker = None

    # 启动定时同步调度器
    app.state.scheduler = SyncScheduler(
        embedding=app.state.embedding,
        vector_store=app.state.vector_store,
    )
    app.state.scheduler.start()
    logger.info("SyncScheduler 已启动")

    # 初始化任务持久化存储
    task_store = TaskStore()
    app.state.task_store = task_store
    task_manager.set_store(task_store)
    task_manager.load_from_store()

    # 注入 TaskStore 到各模块
    from delphi.evaluation.dataset import set_task_store as set_dataset_store
    from delphi.evaluation.runner import set_task_store as set_eval_store
    from delphi.ingestion.pipeline import set_task_store as set_pipeline_store
    set_pipeline_store(task_store)
    set_eval_store(task_store)
    set_dataset_store(task_store)

    logger.info("Delphi v{} 启动完成, 监听 {}:{}", __version__, settings.host, settings.port)
    yield

    # 停止调度器
    logger.info("Delphi 正在关闭...")
    await app.state.scheduler.stop()
    logger.debug("Scheduler 已停止")
    await app.state.embedding.close()
    logger.debug("EmbeddingClient 已关闭")
    await app.state.vector_store.close()
    logger.debug("VectorStore 已关闭")
    if app.state.reranker:
        await app.state.reranker.close()
        logger.debug("RerankerClient 已关闭")
    logger.info("Delphi 已完全关闭")


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
app.include_router(settings_routes.router)
app.include_router(eval_routes.router)


# ---- WebSocket 端点 ----


@app.websocket("/ws/tasks")
async def websocket_all_tasks(websocket: WebSocket) -> None:
    await ws_all_tasks(websocket)


@app.websocket("/ws/tasks/{task_id}")
async def websocket_single_task(websocket: WebSocket, task_id: str) -> None:
    await ws_single_task(websocket, task_id)
