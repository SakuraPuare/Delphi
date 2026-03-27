from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from delphi import __version__
from delphi.api.routes import agent, finetune, graph, health, import_, models, openai_compat, projects, query
from delphi.core.clients import EmbeddingClient, VectorStore
from delphi.core.config import settings
from delphi.graph.store import GraphStore
from delphi.models.manager import ModelManager
from delphi.retrieval.rag import RerankerClient
from delphi.retrieval.session import SessionStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedding = EmbeddingClient()
    app.state.vector_store = VectorStore()
    app.state.sessions = SessionStore()
    app.state.model_manager = ModelManager()
    app.state.graph_store = GraphStore()
    if settings.reranker_enabled:
        app.state.reranker = RerankerClient()
    else:
        app.state.reranker = None
    yield
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
