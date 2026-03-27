# 测试指南

## 概述

Delphi 采用三层测试策略，确保从单个函数到完整用户流程的各个层面都有覆盖：

- **单元测试** — 验证独立模块的核心逻辑（chunker、RAG 去重、intent 分类等）
- **集成测试** — 验证多个模块协作的正确性（API 端点、导入流水线、RAG 检索链路）
- **E2E 测试** — 模拟真实用户场景，从数据导入到查询回答的完整流程

所有测试均使用内存 Qdrant + fake embedding + mock LLM，无需启动任何外部服务即可运行。

## 测试目录结构

```
tests/
├── __init__.py
├── test_agent.py            # Agent 模块单元测试
├── test_api_routes.py       # API 路由单元测试
├── test_chunker.py          # Tree-sitter chunker 单元测试
├── test_cli.py              # CLI 命令单元测试
├── test_clients.py          # 客户端封装单元测试
├── test_doc_chunker.py      # 文档 chunker 单元测试
├── test_finetune.py         # 微调模块单元测试
├── test_generate.py         # 生成模块单元测试
├── test_git.py              # Git 导入单元测试
├── test_graph.py            # 知识图谱单元测试
├── test_health.py           # 健康检查单元测试
├── test_incremental.py      # 增量导入单元测试
├── test_integration.py      # 综合集成单元测试
├── test_intent.py           # 意图分类单元测试
├── test_models.py           # 模型管理单元测试
├── test_rag.py              # RAG 检索单元测试
├── test_session.py          # 会话管理单元测试
├── integration/
│   ├── __init__.py
│   ├── conftest.py          # 集成测试共享 fixtures
│   ├── test_api_endpoints.py      # API 端点集成测试
│   ├── test_ingestion_pipeline.py # 导入流水线集成测试
│   └── test_rag_pipeline.py       # RAG 完整链路集成测试
└── e2e/
    ├── __init__.py
    └── test_query_flow.py   # 导入→查询完整 E2E 测试
```

## 运行测试

项目使用 [pytest](https://docs.pytest.org/) 作为测试框架，配合 `pytest-asyncio` 处理异步测试。

### 全部测试

```bash
pytest
```

### 仅单元测试

```bash
pytest tests/ -k "not integration and not e2e"
```

### 仅集成测试

```bash
pytest tests/integration/
```

### 仅 E2E 测试

```bash
pytest tests/e2e/
```

### 带覆盖率报告

```bash
pytest --cov=delphi --cov-report=term-missing
```

生成 HTML 格式的覆盖率报告：

```bash
pytest --cov=delphi --cov-report=html
# 报告输出到 htmlcov/ 目录，用浏览器打开 htmlcov/index.html 查看
```

::: tip
`pyproject.toml` 中已配置 `asyncio_mode = "auto"`，异步测试函数无需手动添加 `@pytest.mark.asyncio` 装饰器（但显式添加也不会出错）。
:::

## 测试 Fixtures

共享 fixtures 定义在 `tests/integration/conftest.py`，为集成测试提供统一的 mock 基础设施。

### `vector_store`

内存模式的 Qdrant 向量存储，测试结束后自动关闭：

```python
@pytest.fixture
async def vector_store():
    client = AsyncQdrantClient(location=":memory:")
    vs = VectorStore(client=client)
    yield vs
    await vs.close()
```

### `fake_embedding`

确定性的 fake embedding 客户端。相同文本始终生成相同向量，保证测试可重复：

```python
class FakeEmbedding:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 基于文本 hash 的确定性向量
        ...

    async def embed_all(self, texts: list[str]) -> EmbeddingResult:
        # 同时返回 dense + sparse 向量
        ...
```

### `session_store`

空的会话存储实例，用于测试多轮对话：

```python
@pytest.fixture
def session_store():
    return SessionStore()
```

### `mock_reranker`

Mock reranker，按原始顺序返回前 N 个结果：

```python
@pytest.fixture
def mock_reranker():
    reranker = AsyncMock()
    async def _rerank(query, texts, top_k=None):
        n = top_k or len(texts)
        return [(i, 1.0 - i * 0.1) for i in range(min(n, len(texts)))]
    reranker.rerank = _rerank
    return reranker
```

### `test_client`

带 mock lifespan 的 FastAPI `TestClient`，注入所有 mock 依赖，可直接发送 HTTP 请求：

```python
@pytest.fixture()
def test_client(fake_embedding, session_store):
    # 替换 app lifespan，注入 mock 的 embedding、vector_store 等
    ...
    with TestClient(app) as c:
        yield c, mock_vs, fake_embedding
```

## Mock 策略

测试中需要 mock 三类外部依赖：LLM 推理服务、向量存储、Embedding 模型。

### Mock LLM

LLM 调用通过 `unittest.mock.patch` 替换，避免依赖真实推理服务：

```python
from unittest.mock import AsyncMock, patch

# Mock 同步生成
@patch("delphi.retrieval.rag.generate_sync")
async def test_rewrite(mock_gen):
    mock_gen.return_value = "改写后的查询"
    result = await rewrite_query("原始问题", "http://fake:8000", "model")
    assert result == "改写后的查询"

# Mock 流式生成（异步生成器）
async def _fake_generate(messages, url, model):
    yield "hello"
    yield " world"

with patch("delphi.api.routes.query.generate", side_effect=_fake_generate):
    resp = client.post("/query/stream", json={...})
```

### Mock 向量存储

使用 `AsyncQdrantClient(location=":memory:")` 创建内存实例，无需启动 Qdrant 服务。对于不需要真实存储逻辑的场景，直接用 `AsyncMock`：

```python
vector_store = AsyncMock()
vector_store.search = AsyncMock(return_value=[mock_scored_point])
vector_store.ensure_collection = AsyncMock()
```

### Mock Embedding

使用 `FakeEmbedding` 类替代真实 embedding 模型。它基于文本 hash 生成确定性向量，保证：

- 相同文本 → 相同向量（测试可重复）
- 同时提供 dense 和 sparse 向量（匹配真实接口）
- 无需下载或加载任何模型权重

### Mock FastAPI Lifespan

测试 API 端点时，需要替换 `app.router.lifespan_context` 注入 mock 依赖：

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def _test_lifespan(a):
    a.state.embedding = fake_embedding
    a.state.vector_store = mock_vs
    a.state.reranker = None
    a.state.sessions = SessionStore()
    yield

app.router.lifespan_context = _test_lifespan
with TestClient(app) as client:
    # 发送请求...
```

## 编写新测试

### 单元测试

在 `tests/` 根目录下创建 `test_<模块名>.py`，直接导入被测模块：

```python
from delphi.ingestion.chunker import chunk_file, detect_language

def test_detect_language():
    assert detect_language(Path("foo.py")) == "python"
    assert detect_language(Path("bar.ts")) == "typescript"

def test_chunk_file_python(tmp_path: Path):
    py_file = tmp_path / "example.py"
    py_file.write_text("def foo():\n    return 1\n")
    chunks = chunk_file(py_file)
    assert len(chunks) >= 1
```

要点：
- 使用 pytest 内置的 `tmp_path` fixture 创建临时文件
- 测试函数名以 `test_` 开头，用类组织相关测试（如 `TestDeduplication`）
- 对外部依赖使用 `patch` / `AsyncMock`

### 集成测试

在 `tests/integration/` 下创建测试文件，使用 `conftest.py` 中的共享 fixtures：

```python
from .conftest import FakeEmbedding

@pytest.fixture
def embedding():
    return FakeEmbedding()

class TestMyFeature:
    async def test_something(self, vector_store, embedding):
        # 使用内存 Qdrant + fake embedding 测试
        ...
```

### E2E 测试

E2E 测试模拟完整用户流程。参考 `tests/e2e/test_query_flow.py` 的模式：

1. 创建临时代码仓库（`tmp_path`）
2. 执行导入流水线（`run_git_import`）
3. 通过 RAG 检索验证结果
4. 通过 API 端点验证 HTTP 响应

```python
async def test_full_flow(self, tmp_path):
    repo = _create_test_repo(tmp_path)
    vs = VectorStore(client=AsyncQdrantClient(location=":memory:"))
    emb = FakeEmbedding()

    # 导入
    await run_git_import(str(repo), project="test", embedding=emb, vector_store=vs)

    # 检索
    chunks = await retrieve(question="...", project="test",
                            embedding_client=emb, vector_store=vs)
    assert len(chunks) > 0
```

### 命名规范

- 测试文件：`test_<模块名>.py`
- 测试类：`Test<功能描述>`（如 `TestFullRAGPipeline`、`TestDeduplication`）
- 测试方法：`test_<行为描述>`（如 `test_exact_duplicate_removal`）
- 用中文 docstring 描述测试意图

## 覆盖率报告

项目使用 `pytest-cov` 生成覆盖率报告。

```bash
# 终端输出，显示未覆盖的行号
pytest --cov=delphi --cov-report=term-missing

# HTML 报告
pytest --cov=delphi --cov-report=html

# 同时生成多种格式
pytest --cov=delphi --cov-report=term-missing --cov-report=html
```

建议关注以下模块的覆盖率：

| 模块 | 说明 |
|------|------|
| `delphi.ingestion` | 数据导入（chunker、git、增量更新） |
| `delphi.retrieval` | RAG 检索（retrieve、rerank、去重） |
| `delphi.api` | API 路由和端点 |
| `delphi.core` | 核心客户端封装 |
