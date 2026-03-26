# 功能：API 服务

## 功能描述

Delphi API Server 是系统的核心后端，基于 FastAPI + Uvicorn 实现，向上为 Web UI 和 CLI 提供统一接口，向下协调 [vLLM](/concepts/tools/vllm)、[Qdrant](/concepts/tools/qdrant)、[BGE-M3](/concepts/tools/bgem3) 等服务完成 [RAG](/concepts/core/rag) 流程。

## 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 自动生成 OpenAPI 文档，原生支持异步 |
| ASGI 服务器 | Uvicorn | 高性能异步服务器 |
| 流式响应 | SSE（Server-Sent Events） | 用于问答接口的逐 token 输出 |
| 数据校验 | Pydantic v2 | 请求/响应模型定义 |

## API 设计原则

- 所有接口使用 JSON 格式（`Content-Type: application/json`）
- 流式问答接口使用 SSE（`text/event-stream`）
- 错误响应统一格式，包含 `code` 和 `message` 字段
- MVP 阶段认证可选：通过 `X-API-Key` 请求头传递，留空则跳过认证
- 遵循 RESTful 语义：`GET` 查询，`POST` 创建，`DELETE` 删除

## 完整端点列表

### 系统

#### `GET /health`

健康检查，供 Docker 健康检测和监控使用。

**响应：**
```json
{ "status": "ok", "version": "0.1.0" }
```

#### `GET /status`

返回各后端服务的连通状态。

**响应：**
```json
{
  "vllm": { "ok": true, "model": "Qwen2.5-7B-Instruct" },
  "qdrant": { "ok": true, "collections": 2 },
  "embedding": { "ok": true, "model": "BAAI/bge-m3" }
}
```

---

### 项目管理

#### `GET /projects`

列出所有项目。

**响应：**
```json
[
  { "name": "myproject", "chunk_count": 1893, "created_at": "2024-01-15T10:23:00Z" }
]
```

#### `POST /projects`

创建项目（同时在 Qdrant 中创建对应 Collection）。

**请求体：**
```json
{ "name": "myproject", "description": "可选描述" }
```

**响应：** `201 Created`，返回项目对象。

#### `DELETE /projects/{name}`

删除项目及其所有向量数据。

**响应：** `204 No Content`

---

### 文档导入

#### `POST /import/git`

异步导入 Git 仓库，立即返回任务 ID。

**请求体：**
```json
{
  "url": "https://github.com/org/repo",
  "project": "myproject",
  "branch": "main",
  "include": ["**/*.md"],
  "exclude": [],
  "depth": 1
}
```

**响应：** `202 Accepted`
```json
{ "task_id": "abc123", "status": "pending" }
```

#### `POST /import/docs`

异步导入本地目录（路径为服务器端路径）。

**请求体：**
```json
{
  "path": "/data/docs",
  "project": "myproject",
  "recursive": true,
  "file_types": ["md", "txt", "pdf"]
}
```

**响应：** `202 Accepted`，同上。

#### `GET /tasks/{task_id}`

查询导入任务进度。

**响应：**
```json
{
  "task_id": "abc123",
  "status": "running",
  "progress": 0.78,
  "total": 142,
  "processed": 111,
  "error": null
}
```

`status` 枚举值：`pending` | `running` | `done` | `failed`

---

### 问答

#### `POST /query`

非流式问答，等待完整回答后返回。

**请求体：**
```json
{
  "question": "如何配置 vLLM 并发数？",
  "project": "myproject",
  "top_k": 5,
  "stream": false
}
```

**响应：**
```json
{
  "answer": "vLLM 通过 --max-num-seqs 参数...",
  "sources": [
    { "file": "docs/vllm.md", "chunk": "...", "score": 0.92 }
  ]
}
```

#### `POST /query/stream`

流式问答，使用 SSE 逐 token 推送。

**请求体：** 同 `/query`（`stream` 字段忽略）

**响应：** `Content-Type: text/event-stream`

```
data: {"token": "vLLM"}
data: {"token": " 通过"}
data: {"token": " --max-num-seqs"}
...
data: {"done": true, "sources": [...]}
```

---

## 错误响应格式

所有错误统一返回：

```json
{
  "code": "PROJECT_NOT_FOUND",
  "message": "项目 'myproject' 不存在"
}
```

常见错误码：

| HTTP 状态码 | code | 说明 |
|-------------|------|------|
| `400` | `INVALID_REQUEST` | 请求参数错误 |
| `401` | `UNAUTHORIZED` | API Key 无效 |
| `404` | `PROJECT_NOT_FOUND` | 项目不存在 |
| `404` | `TASK_NOT_FOUND` | 任务不存在 |
| `500` | `UPSTREAM_ERROR` | 上游服务（vLLM/Qdrant）异常 |

## 认证方案

MVP 阶段认证为可选项。若 `config.yaml` 中设置了 `api_key`，则所有请求需携带：

```
X-API-Key: <your-api-key>
```

`/health` 端点始终不需要认证。

## CORS 配置

默认允许所有来源（开发模式），生产部署时建议限制为 Web UI 的域名：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 与后端服务的通信

| 后端服务 | 通信方式 | 说明 |
|----------|----------|------|
| vLLM | HTTP，OpenAI 兼容接口 | `POST /v1/chat/completions` |
| Qdrant | HTTP REST 或 Python SDK | 向量检索与集合管理 |
| Embedding | HTTP，HuggingFace TEI 接口 | `POST /embed` |

所有后端通信均使用 `httpx.AsyncClient` 异步调用，避免阻塞事件循环。

## 交互式文档

服务启动后，访问以下地址查看自动生成的 API 文档：

- Swagger UI：`http://localhost:8888/docs`
- ReDoc：`http://localhost:8888/redoc`
