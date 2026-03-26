# API 接口

Delphi 提供 RESTful API，支持问答、数据导入和系统管理。

## 基础信息

- Base URL: `http://localhost:8000/api`
- Content-Type: `application/json`
- 流式响应: Server-Sent Events (SSE)

## 问答接口

### POST /api/chat

发起问答请求。

**请求体**：

```json
{
  "query": "CyberRT 的组件注册机制是怎样的？",
  "project": "apollo",
  "stream": true,
  "options": {
    "top_k": 20,
    "rerank_top_n": 5,
    "temperature": 0.1,
    "max_tokens": 4096
  }
}
```

**流式响应**（SSE）：

```
data: {"type": "chunk", "content": "CyberRT 的组件注册"}
data: {"type": "chunk", "content": "通过 ComponentBase 类实现..."}
data: {"type": "sources", "sources": [{"file": "cyber/component/component.h", "line": 42, "score": 0.92}]}
data: {"type": "done"}
```

**非流式响应**：

```json
{
  "answer": "CyberRT 的组件注册通过 ComponentBase 类实现...",
  "sources": [
    {
      "file": "cyber/component/component.h",
      "line": 42,
      "score": 0.92,
      "content": "class ComponentBase { ... }"
    }
  ]
}
```

### POST /api/chat/history

获取对话历史。

```json
{
  "session_id": "abc123",
  "limit": 20
}
```

## 数据导入接口

### POST /api/import/git

导入 Git 仓库。

```json
{
  "url": "https://github.com/ApolloAuto/apollo.git",
  "branch": "master",
  "project": "apollo",
  "exclude_patterns": ["**/third_party/**"]
}
```

### POST /api/import/docs

导入文档目录。

```json
{
  "path": "/data/docs",
  "project": "apollo",
  "formats": ["md", "html", "pdf"]
}
```

### POST /api/import/media

导入音视频文件。

```json
{
  "path": "/data/videos",
  "project": "apollo",
  "language": "auto"
}
```

### GET /api/import/status

查询导入任务状态。

```json
{
  "task_id": "import_abc123",
  "status": "processing",
  "progress": {
    "total_files": 15000,
    "processed_files": 8500,
    "total_chunks": 120000,
    "elapsed_seconds": 3600
  }
}
```

## 项目管理接口

### GET /api/projects

列出所有项目。

```json
{
  "projects": [
    {
      "name": "apollo",
      "chunk_count": 150000,
      "last_updated": "2025-03-20T10:00:00Z"
    }
  ]
}
```

### DELETE /api/projects/{name}

删除项目及其所有数据。

## 系统接口

### GET /api/health

健康检查。

```json
{
  "status": "ok",
  "services": {
    "vllm": "ok",
    "qdrant": "ok",
    "embedding": "ok",
    "reranker": "ok"
  }
}
```

### GET /api/stats

系统统计信息。

```json
{
  "total_chunks": 150000,
  "total_projects": 1,
  "qdrant_memory_mb": 14000,
  "gpu_memory_used_mb": 20000,
  "uptime_seconds": 86400
}
```
