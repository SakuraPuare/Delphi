# API 接口文档

Delphi 提供 RESTful API，支持知识库问答、数据导入、项目管理、模型管理、代码图谱、微调数据生成、定时任务调度以及 WebSocket 实时推送。

## 基础信息

- Base URL: `http://localhost:8888`
- Content-Type: `application/json`
- 流式响应: Server-Sent Events (SSE)
- 实时推送: WebSocket
- 所有路由均在根路径下，无 `/api` 前缀

## 健康检查与状态

### GET /health

检查服务是否存活。

**响应** `200 OK`：

```json
{
  "status": "ok",
  "version": "0.3.0"
}
```

### GET /status

查询各依赖服务的运行状态。

**响应** `200 OK`：

```json
{
  "vllm": { "status": "healthy", "latency_ms": 12 },
  "qdrant": { "status": "healthy", "latency_ms": 3 },
  "embedding": { "status": "healthy", "latency_ms": 5 }
}
```

## 项目管理

### GET /projects

获取所有项目列表。

**响应** `200 OK`：

```json
[
  {
    "name": "apollo",
    "description": "Apollo 自动驾驶平台源码",
    "chunk_count": 150000,
    "created_at": "2026-03-20T10:00:00Z"
  }
]
```

### POST /projects

创建新项目。

**请求体**：

```json
{
  "name": "apollo",
  "description": "Apollo 自动驾驶平台源码"
}
```

**响应** `201 Created`：

```json
{
  "name": "apollo",
  "description": "Apollo 自动驾驶平台源码",
  "chunk_count": 0,
  "created_at": "2026-03-28T08:00:00Z"
}
```

| 状态码 | 说明 |
|--------|------|
| 201 | 创建成功 |
| 409 | 项目名已存在 |
| 422 | 请求体校验失败 |

### DELETE /projects/{name}

删除项目及其所有数据（向量、图谱等）。

**路径参数**：`name` — 项目名称

**响应** `204 No Content`：无响应体

| 状态码 | 说明 |
|--------|------|
| 204 | 删除成功 |
| 404 | 项目不存在 |

## 数据导入

所有导入接口均为异步操作，返回 `TaskInfo` 对象，可通过任务 ID 轮询进度或使用 WebSocket 订阅。

### POST /import/git

导入 Git 仓库代码。

**请求体**：

```json
{
  "url": "https://github.com/ApolloAuto/apollo.git",
  "project": "apollo",
  "branch": "main",
  "include": ["modules/planning/**", "modules/perception/**"],
  "exclude": ["**/third_party/**", "**/test/**"],
  "depth": 1
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 是 | — | Git 仓库地址 |
| project | string | 是 | — | 目标项目名 |
| branch | string | 否 | `"main"` | 分支名 |
| include | list[string] | 否 | `[]` | 包含的 glob 模式（空表示全部） |
| exclude | list[string] | 否 | `[]` | 排除的 glob 模式 |
| depth | int | 否 | `1` | git clone 深度 |

**响应** `202 Accepted`：

```json
{
  "task_id": "task_a1b2c3d4",
  "status": "pending",
  "progress": 0,
  "total": 0,
  "processed": 0,
  "error": null
}
```

### POST /import/docs

导入本地文档目录。

**请求体**：

```json
{
  "path": "/data/docs/apollo",
  "project": "apollo",
  "recursive": true,
  "file_types": ["md", "txt", "pdf", "html"]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| path | string | 是 | — | 文档目录路径 |
| project | string | 是 | — | 目标项目名 |
| recursive | bool | 否 | `true` | 是否递归扫描子目录 |
| file_types | list[string] | 否 | `["md","txt","pdf","html"]` | 要处理的文件类型 |

**响应** `202 Accepted`：同 TaskInfo 格式。

### POST /import/media

导入音视频文件，使用 Whisper 进行语音转文字后入库。

**请求体**：

```json
{
  "path": "/data/videos/lectures",
  "project": "apollo",
  "recursive": true,
  "whisper_model": "large-v3"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| path | string | 是 | — | 音视频文件目录 |
| project | string | 是 | — | 目标项目名 |
| recursive | bool | 否 | `true` | 是否递归扫描子目录 |
| whisper_model | string | 否 | `"large-v3"` | Whisper 模型版本 |

**响应** `202 Accepted`：同 TaskInfo 格式。

### POST /import/batch

批量导入多个 Git 仓库。

**请求体**：

```json
{
  "repos": [
    { "url": "https://github.com/ApolloAuto/apollo.git", "branch": "main", "project_name": "apollo" },
    { "url": "https://github.com/autowarefoundation/autoware.git", "branch": "main", "project_name": "autoware" }
  ],
  "depth": 1,
  "include": [],
  "exclude": ["**/test/**"]
}
```

**响应** `202 Accepted`：

```json
{
  "tasks": [
    { "task_id": "task_a1b2c3d4", "status": "pending", "progress": 0, "total": 0, "processed": 0, "error": null },
    { "task_id": "task_e5f6g7h8", "status": "pending", "progress": 0, "total": 0, "processed": 0, "error": null }
  ]
}
```

### GET /import/tasks/{task_id}

查询导入任务的执行状态。

**路径参数**：`task_id` — 任务 ID

**响应** `200 OK`：

```json
{
  "task_id": "task_a1b2c3d4",
  "status": "processing",
  "progress": 65,
  "total": 15000,
  "processed": 9750,
  "error": null
}
```

`status` 可选值：`pending` | `processing` | `completed` | `failed`

| 状态码 | 说明 |
|--------|------|
| 200 | 查询成功 |
| 404 | 任务不存在 |

## 知识库问答

### POST /query

对指定项目发起 RAG 问答。

**请求体**：

```json
{
  "question": "CyberRT 的组件注册机制是怎样的？",
  "project": "apollo",
  "top_k": 5,
  "session_id": null,
  "use_graph_rag": true
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| question | string | 是 | — | 用户问题 |
| project | string | 是 | — | 项目名 |
| top_k | int | 否 | `5` | 检索返回的 chunk 数量 |
| session_id | string | 否 | `null` | 会话 ID，传入可保持多轮对话上下文 |
| use_graph_rag | bool | 否 | `true` | 是否启用 Graph RAG 增强检索 |

**响应** `200 OK`：

```json
{
  "answer": "CyberRT 的组件注册通过 ComponentBase 类实现，开发者继承该基类并在 Init() 中完成初始化...",
  "sources": [
    {
      "index": 0,
      "file": "cyber/component/component.h",
      "chunk": "class ComponentBase {\n public:\n  virtual bool Init() = 0;\n  ...\n}",
      "score": 0.92,
      "start_line": 35,
      "end_line": 78
    }
  ],
  "session_id": "sess_x9y8z7"
}
```

### POST /query/stream

流式问答，通过 Server-Sent Events 逐步返回结果。请求体与 `POST /query` 相同。

**SSE 事件流**：

```
data: {"type": "token", "content": "CyberRT 的组件注册"}

data: {"type": "token", "content": "通过 ComponentBase 类实现..."}

data: {"type": "sources", "sources": [{"index": 0, "file": "cyber/component/component.h", "chunk": "...", "score": 0.92, "start_line": 35, "end_line": 78}]}

data: {"type": "done", "session_id": "sess_x9y8z7"}
```

**事件类型**：

| type | 说明 |
|------|------|
| `token` | 生成的文本片段 |
| `sources` | 检索到的来源列表 |
| `done` | 生成完成，包含 session_id |
| `error` | 发生错误，包含 message 字段 |

::: tip
流式接口适合前端实时展示生成过程，减少用户等待感。使用 `EventSource` 或 `fetch` + `ReadableStream` 消费。
:::

## Agent 问答

Agent 模式支持多步推理，模型会自主拆解问题、检索信息并逐步得出答案。

### POST /agent/query

发起 Agent 多步推理问答。

**请求体**：

```json
{
  "question": "Apollo Planning 模块的决策流程是怎样的？涉及哪些关键类？",
  "project": "apollo",
  "max_steps": 5,
  "session_id": null
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| question | string | 是 | — | 用户问题 |
| project | string | 是 | — | 项目名 |
| max_steps | int | 否 | `5` | 最大推理步数 |
| session_id | string | 否 | `null` | 会话 ID |

**响应** `200 OK`：

```json
{
  "answer": "Apollo Planning 模块的决策流程分为...",
  "steps": [
    {
      "thought": "需要先了解 Planning 模块的入口类",
      "action": "search: PlanningComponent Init",
      "observation": "找到 modules/planning/planning_component.cc ...",
      "answer": null
    },
    {
      "thought": "已找到关键类，可以总结",
      "action": null,
      "observation": null,
      "answer": "Apollo Planning 模块的决策流程分为..."
    }
  ],
  "sources": [
    { "index": 0, "file": "modules/planning/planning_component.cc", "chunk": "...", "score": 0.91, "start_line": 10, "end_line": 55 }
  ],
  "session_id": "sess_abc123"
}
```

### POST /agent/query/stream

Agent 流式问答，通过 SSE 实时推送推理过程。请求体与 `POST /agent/query` 相同。

**SSE 事件流**：

```
data: {"type": "thought", "content": "需要先了解 Planning 模块的入口类"}

data: {"type": "action", "content": "search: PlanningComponent Init"}

data: {"type": "observation", "content": "找到 modules/planning/planning_component.cc ..."}

data: {"type": "token", "content": "Apollo Planning 模块"}

data: {"type": "token", "content": "的决策流程分为..."}

data: {"type": "sources", "sources": [...]}

data: {"type": "done", "session_id": "sess_abc123"}
```

**事件类型**：

| type | 说明 |
|------|------|
| `thought` | Agent 的思考过程 |
| `action` | Agent 执行的动作 |
| `observation` | 动作执行结果 |
| `token` | 最终回答的文本片段 |
| `sources` | 检索来源 |
| `done` | 推理完成 |

## 模型管理

### GET /models

获取所有已注册模型。

**响应** `200 OK`：

```json
[
  {
    "name": "qwen2.5-coder-7b",
    "model_path": "/models/qwen2.5-coder-7b-instruct-awq",
    "model_type": "base",
    "base_model": "",
    "description": "通用代码问答模型",
    "active": true
  }
]
```

### POST /models/register

注册新模型。

**请求体**：

```json
{
  "name": "apollo-lora-v1",
  "model_path": "/models/apollo-lora-v1",
  "model_type": "lora",
  "base_model": "qwen2.5-coder-7b",
  "description": "基于 Apollo 代码微调的 LoRA 适配器"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | string | 是 | — | 模型名称 |
| model_path | string | 是 | — | 模型文件路径 |
| model_type | string | 否 | `"base"` | 模型类型：`base` 或 `lora` |
| base_model | string | 否 | `""` | LoRA 适配器对应的基座模型名 |
| description | string | 否 | `""` | 模型描述 |

**响应** `201 Created`：返回 ModelInfoResponse 对象。

| 状态码 | 说明 |
|--------|------|
| 201 | 注册成功 |
| 409 | 模型名已存在 |
| 422 | 请求体校验失败 |

### DELETE /models/{name}

删除已注册的模型。

**路径参数**：`name` — 模型名称

**响应** `204 No Content`

| 状态码 | 说明 |
|--------|------|
| 204 | 删除成功 |
| 404 | 模型不存在 |

### POST /models/activate

激活指定模型，vLLM 将加载该模型用于推理。

**请求体**：

```json
{
  "name": "apollo-lora-v1"
}
```

**响应** `200 OK`：返回被激活模型的 ModelInfoResponse 对象。

::: warning
激活模型会触发 vLLM 重新加载，期间推理服务短暂不可用。
:::

## 微调数据生成

### POST /finetune/generate

基于项目已有的 chunk 自动生成微调训练数据（QA 对）。

**请求体**：

```json
{
  "project": "apollo",
  "num_samples": 100,
  "questions_per_chunk": 2,
  "format": "jsonl",
  "output_path": ""
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| project | string | 是 | — | 项目名 |
| num_samples | int | 否 | `100` | 生成的样本数量 |
| questions_per_chunk | int | 否 | `2` | 每个 chunk 生成的问题数 |
| format | string | 否 | `"jsonl"` | 输出格式 |
| output_path | string | 否 | `""` | 自定义输出路径，为空则使用默认路径 |

**响应** `202 Accepted`：返回 TaskInfo 对象。

### GET /finetune/tasks/{task_id}

查询微调数据生成任务的状态。

**路径参数**：`task_id` — 任务 ID

**响应** `200 OK`：返回 TaskInfo 对象。

## 代码图谱

Graph RAG 基于代码的 AST 解析构建符号关系图谱，用于增强检索精度。

### POST /graph/build

为项目构建代码图谱。

**请求体**：

```json
{
  "project": "apollo",
  "path": "modules/planning",
  "include": ["*.cc", "*.h"],
  "exclude": ["*_test.cc"]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| project | string | 是 | — | 项目名 |
| path | string | 是 | — | 要解析的代码路径 |
| include | list[string] | 否 | `[]` | 包含的 glob 模式 |
| exclude | list[string] | 否 | `[]` | 排除的 glob 模式 |

**响应** `202 Accepted`：返回 TaskInfo 对象。

### GET /graph/{project}

查询项目的完整图谱。

**路径参数**：`project` — 项目名

**响应** `200 OK`：

```json
{
  "symbols": [
    {
      "name": "PlanningComponent",
      "qualified_name": "apollo::planning::PlanningComponent",
      "kind": "class",
      "file_path": "modules/planning/planning_component.h",
      "start_line": 28,
      "end_line": 65,
      "language": "cpp"
    }
  ],
  "relations": [
    {
      "source": "apollo::planning::PlanningComponent",
      "target": "apollo::cyber::Component",
      "kind": "inherits"
    }
  ]
}
```

### GET /graph/{project}/symbol/{name}

按符号名查询相关的符号和关系。

**路径参数**：
- `project` — 项目名
- `name` — 符号名称

**响应** `200 OK`：返回 GraphQueryResponse 对象（格式同上）。

### GET /graph/{project}/file/{path}

按文件路径查询该文件中的所有符号和关系。

**路径参数**：
- `project` — 项目名
- `path` — 文件路径

**响应** `200 OK`：返回 GraphQueryResponse 对象。

## 定时任务调度

管理项目的定时同步任务，支持 cron 表达式配置。

### POST /scheduler/jobs

创建定时同步任务。

**请求体**：

```json
{
  "project_id": "apollo",
  "repo_url": "https://github.com/ApolloAuto/apollo.git",
  "cron_expr": "0 */6 * * *",
  "branch": "main"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| project_id | string | 是 | — | 项目名 |
| repo_url | string | 是 | — | Git 仓库地址 |
| cron_expr | string | 否 | `"0 */6 * * *"` | cron 表达式（默认每 6 小时） |
| branch | string | 否 | `"main"` | 分支名 |

**响应** `201 Created`：返回 SchedulerJobInfo 对象。

### GET /scheduler/jobs

获取所有定时任务列表。

**响应** `200 OK`：

```json
[
  {
    "project_id": "apollo",
    "repo_url": "https://github.com/ApolloAuto/apollo.git",
    "cron_expr": "0 */6 * * *",
    "branch": "main",
    "last_run": "2026-03-28T06:00:00Z",
    "next_run": "2026-03-28T12:00:00Z"
  }
]
```

### DELETE /scheduler/jobs/{project_id}

删除定时任务。

**路径参数**：`project_id` — 项目名

**响应** `204 No Content`

### POST /scheduler/jobs/{project_id}/trigger

手动触发一次同步任务。

**路径参数**：`project_id` — 项目名

**响应** `200 OK`：

```json
{
  "detail": "已触发项目 apollo 的同步任务"
}
```

## WebSocket 实时推送

通过 WebSocket 订阅任务进度，避免轮询开销。

### ws://host/ws/tasks

订阅所有任务的进度推送。连接后会收到当前所有活跃任务的快照，随后实时推送进度更新。

### ws://host/ws/tasks/{task_id}

订阅指定任务的进度推送。

**事件格式**：

```json
// 连接时推送当前任务快照
{"event": "snapshot", "task_id": "task_a1b2c3d4", "status": "processing", "progress": 65, "total": 15000, "processed": 9750}

// 进度更新
{"event": "progress", "task_id": "task_a1b2c3d4", "progress": 70, "message": "已处理 10500/15000 个文件"}

// 任务完成
{"event": "done", "task_id": "task_a1b2c3d4", "result": {"chunk_count": 150000}}

// 任务失败
{"event": "failed", "task_id": "task_a1b2c3d4", "error": "Git clone 失败: repository not found"}
```

**事件类型**：

| event | 说明 |
|-------|------|
| `snapshot` | 连接时推送的任务当前状态快照 |
| `progress` | 任务进度更新 |
| `done` | 任务完成 |
| `failed` | 任务失败 |

::: tip
前端可使用原生 `WebSocket` API 连接，推荐配合 `reconnecting-websocket` 库实现自动重连。
:::

## 通用状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 201 | 资源创建成功 |
| 202 | 异步任务已接受 |
| 204 | 删除成功，无响应体 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如名称重复） |
| 422 | 请求体校验失败 |
| 500 | 服务器内部错误 |
| 503 | 依赖服务不可用（如 vLLM 未就绪） |
