from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from delphi import __version__
from delphi.api.routes import health, import_, projects, query


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: 初始化 httpx clients, qdrant connection 等
    yield
    # TODO: 清理资源


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
