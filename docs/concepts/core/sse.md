# Server-Sent Events (SSE) 流式传输

Server-Sent Events（SSE）是一种基于 HTTP 的单向实时通信协议，允许服务器向客户端持续推送数据。在 LLM 应用中，SSE 是实现"打字机效果"流式输出的标准方案。

## 什么是 SSE？

SSE 建立在普通 HTTP 之上，服务器保持连接打开并持续发送数据，客户端通过浏览器内置的 `EventSource` API 接收。

```
客户端                          服务器
  │                               │
  │── GET /stream ──────────────> │
  │                               │
  │<── data: 第一个 token ────── │
  │<── data: 第二个 token ────── │
  │<── data: 第三个 token ────── │
  │<── data: [DONE] ──────────── │
  │                               │
  │        连接关闭               │
```

与 WebSocket 的核心区别在于：SSE 是**单向的**（服务器 → 客户端），而 WebSocket 是双向的。

## 为什么 SSE 适合 LLM 流式输出

LLM 生成文本的过程是逐 token 产生的，每次生成一个 token 后立即发送，用户就能看到实时输出，而不必等待完整响应。

SSE 在这个场景下的优势：

- **基于 HTTP**：无需特殊协议，穿透防火墙和代理无障碍
- **自动重连**：浏览器 `EventSource` 内置断线重连机制
- **轻量**：无握手开销，连接建立后直接推送
- **单向足够**：LLM 输出是单向的，不需要 WebSocket 的双向能力

## SSE 协议格式

SSE 的消息格式非常简单，每条消息由若干字段组成，以空行分隔：

```
data: 这是消息内容\n\n

event: custom-event\n
data: {"key": "value"}\n\n

id: 42\n
data: 带 ID 的消息\n\n

retry: 3000\n\n
```

四个字段说明：

| 字段 | 含义 |
|------|------|
| `data:` | 消息内容，必填，可多行 |
| `event:` | 自定义事件类型，默认为 `message` |
| `id:` | 消息 ID，用于断线重连时恢复位置 |
| `retry:` | 重连等待时间（毫秒） |

HTTP 响应头需要设置：

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

## 浏览器 EventSource API

```javascript
const source = new EventSource('/api/chat/stream')

// 监听默认 message 事件
source.onmessage = (event) => {
  if (event.data === '[DONE]') {
    source.close()
    return
  }
  const chunk = JSON.parse(event.data)
  appendText(chunk.choices[0].delta.content)
}

// 监听自定义事件
source.addEventListener('error-event', (event) => {
  console.error('Stream error:', event.data)
})

source.onerror = () => {
  source.close()
}
```

`EventSource` 不支持 POST 请求和自定义请求头，这是其主要限制。实际项目中通常用 `fetch` + `ReadableStream` 替代：

```javascript
const response = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: '...' })
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  const text = decoder.decode(value)
  // 解析 SSE 格式并处理
}
```

## 服务端实现（FastAPI 示例）

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio

app = FastAPI()

async def generate_stream(query: str):
    # 模拟 LLM 逐 token 输出
    tokens = ["你好", "，", "这是", "流式", "输出", "示例"]
    for token in tokens:
        yield f"data: {token}\n\n"
        await asyncio.sleep(0.05)
    yield "data: [DONE]\n\n"

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        generate_stream(request.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )
```

注意 `X-Accel-Buffering: no` 头，它告诉 Nginx 不要缓冲响应，确保数据实时到达客户端。

## SSE vs WebSocket vs Long Polling

| 特性 | SSE | WebSocket | Long Polling |
|------|-----|-----------|--------------|
| 方向 | 单向（服务器→客户端） | 双向 | 单向 |
| 协议 | HTTP | WS/WSS | HTTP |
| 自动重连 | 是（内置） | 否（需手动） | 否（需手动） |
| 穿透代理 | 容易 | 有时困难 | 容易 |
| 延迟 | 低 | 极低 | 高 |
| 实现复杂度 | 低 | 中 | 中 |
| 适合场景 | LLM 输出、通知推送 | 聊天、游戏 | 兼容性要求高 |

对于 LLM 流式输出，SSE 是最合适的选择：实现简单、HTTP 友好、自动重连。

## Delphi 如何使用 SSE

Delphi 的对话接口使用 SSE 将 LLM 生成的 token 实时推送到前端：

```
用户提问
  → FastAPI 接收请求
  → 检索相关文档块
  → 构建 Prompt
  → 调用 LLM（OpenAI 兼容接口，stream=True）
  → 逐 token 转发给前端（SSE）
  → 前端实时渲染
```

LLM 本身也通过 SSE 返回流式结果，Delphi 作为中间层将其透传给用户，整个链路保持流式，用户无需等待完整回答生成完毕。

## 延伸阅读

- [OpenAI 兼容 API](./openai-api.md) — SSE 在 OpenAI 流式格式中的具体应用
- [检索增强生成 (RAG)](./rag.md) — Delphi 整体架构
- [大语言模型 (LLM)](./llm.md) — LLM 生成过程与 token 输出
