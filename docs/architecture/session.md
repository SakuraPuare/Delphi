# 会话管理

## 概述

Delphi 提供基于内存的会话管理机制，支持多轮对话上下文。用户在查询时可通过 `session_id` 关联历史对话，系统自动将最近的对话历史注入 Prompt，使 LLM 能够理解上下文并给出连贯的回答。

当前处于 MVP 阶段，会话存储在进程内存中，重启后丢失。

## 数据模型

### Message

单条消息，记录一次用户提问或助手回复：

```python
@dataclass
class Message:
    role: str        # "user" | "assistant"
    content: str     # 消息内容
    timestamp: float # 创建时间戳（time.time()）
```

### Session

一次完整的对话会话：

```python
@dataclass
class Session:
    session_id: str          # 16 位十六进制随机 ID（uuid4().hex[:16]）
    project: str             # 关联的项目名称
    messages: list[Message]  # 有序消息列表
    created_at: float        # 会话创建时间戳
```

核心方法：

| 方法 | 说明 |
|------|------|
| `add_user_message(content)` | 追加一条 `role="user"` 的消息 |
| `add_assistant_message(content)` | 追加一条 `role="assistant"` 的消息 |
| `get_history(max_turns=5)` | 返回最近 N 轮对话，格式为 OpenAI messages |

`get_history` 取 `messages[-(max_turns * 2):]`，即最多返回最近 5 轮（10 条消息），输出格式：

```json
[
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]
```

### SessionStore

内存会话存储，管理所有活跃会话：

```python
class SessionStore:
    def __init__(self, max_sessions: int = 1000): ...
    def create(self, project: str) -> Session: ...
    def get(self, session_id: str) -> Session | None: ...
    def delete(self, session_id: str) -> None: ...
```

## 会话生命周期

```
客户端首次请求（不带 session_id）
   ↓
SessionStore.create(project) → 生成 16 位 hex ID
   ↓
响应中返回 session_id
   ↓
客户端后续请求携带 session_id
   ↓
SessionStore.get(session_id) → 加载已有会话
   ↓
追加消息 → 获取历史 → 注入 Prompt
   ↓
进程重启 → 所有会话丢失
```

会话创建的判断逻辑：

- 请求中 `session_id` 为 `null`：自动创建新会话
- 请求中 `session_id` 有值：尝试加载已有会话；若不存在则不创建新会话（`session` 为 `None`）

## 多轮对话流程

以 `/query` 接口为例，完整的多轮对话流程如下：

```
1. 接收请求，解析 session_id
2. 加载或创建 Session
3. session.get_history() → 获取最近对话历史
4. session.add_user_message(question) → 记录用户提问
5. retrieve() → 向量检索相关文档
6. build_prompt(question, chunks, history=history)
   → [system_prompt] + [历史消息...] + [当前用户提问+检索上下文]
7. LLM 生成回答
8. session.add_assistant_message(answer) → 记录助手回复
9. 返回响应（含 session_id）
```

`build_prompt` 将历史消息插入到 system prompt 之后、当前用户消息之前，使 LLM 能感知之前的对话上下文。

## API 使用方式

### 开始新对话

首次请求不传 `session_id`，系统自动创建会话：

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "项目的入口函数在哪里？", "project": "my-project"}'
```

响应：

```json
{
  "answer": "项目的入口函数位于 src/main.py ...",
  "sources": [...],
  "session_id": "a1b2c3d4e5f67890"
}
```

### 继续对话

后续请求携带上一次返回的 `session_id`：

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "这个函数接受哪些参数？",
    "project": "my-project",
    "session_id": "a1b2c3d4e5f67890"
  }'
```

此时 LLM 能理解"这个函数"指的是上一轮提到的入口函数。

### 支持会话的接口

| 接口 | 说明 |
|------|------|
| `POST /query` | 标准 RAG 查询 |
| `POST /query/stream` | 流式 RAG 查询（SSE） |
| `POST /agent/query` | Agent 多步推理查询 |
| `POST /agent/query/stream` | Agent 流式查询（SSE） |

流式接口在 `done` 事件中返回 `session_id`：

```json
data: {"type": "done", "session_id": "a1b2c3d4e5f67890"}
```

## 存储策略与限制

| 项目 | 说明 |
|------|------|
| 存储方式 | 进程内存（Python dict） |
| 最大会话数 | 1000（`max_sessions` 参数） |
| 淘汰策略 | 超过上限时删除 `created_at` 最早的会话 |
| 持久化 | 无，进程重启后全部丢失 |
| 并发安全 | 单进程安全；多 worker 时各进程独立，session 不共享 |
| 历史窗口 | 默认最近 5 轮（10 条消息） |

淘汰实现：

```python
def _evict_if_needed(self) -> None:
    if len(self._sessions) > self._max_sessions:
        oldest_id = min(self._sessions, key=lambda k: self._sessions[k].created_at)
        del self._sessions[oldest_id]
```

注意：当前淘汰策略基于 `created_at`（创建时间），而非最后访问时间，严格来说是 FIFO 而非 LRU。如需真正的 LRU 语义，可改用 `OrderedDict` 或在 `get()` 时更新时间戳。

## 未来规划

### 持久化存储

MVP 之后计划引入持久化方案，候选：

- **Redis**：适合分布式部署，天然支持 TTL 过期、多 worker 共享
- **SQLite / PostgreSQL**：适合需要查询历史记录、审计日志的场景

### 其他演进方向

- **会话过期**：基于最后活跃时间自动清理不活跃会话（TTL）
- **真正的 LRU**：淘汰策略从 FIFO 改为基于最后访问时间
- **会话摘要**：对话轮数过多时，对早期历史进行摘要压缩，减少 token 消耗
- **多 worker 共享**：通过 Redis 等外部存储实现跨进程会话共享
- **用户绑定**：引入认证后，将 session 与用户 ID 关联
