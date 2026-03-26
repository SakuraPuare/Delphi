# OpenAI 兼容 API

OpenAI API 格式已成为 LLM 服务的事实标准。无论是云端模型还是本地部署的开源模型，绝大多数都提供兼容 OpenAI 格式的接口，这让模型切换变得极为简单。

## 什么是 OpenAI API 格式？

OpenAI API 是 OpenAI 公司为其 GPT 系列模型设计的 HTTP REST API。它定义了一套标准的请求和响应格式，涵盖对话补全、嵌入生成等核心功能。

由于 OpenAI 是最早大规模商业化 LLM API 的公司，大量工具和框架都基于这套格式构建，后来的模型提供商为了兼容这些生态，纷纷实现了相同的接口格式。

## 为什么它成为事实标准？

- **先发优势**：OpenAI 是最早提供成熟 LLM API 的公司，生态最先围绕它建立
- **设计简洁**：接口设计直观，学习成本低
- **工具链完善**：LangChain、LlamaIndex 等框架原生支持
- **开源跟进**：vLLM、Ollama 等本地推理框架主动实现兼容层

## 核心端点

### /v1/chat/completions

对话补全接口，最常用的端点：

```http
POST /v1/chat/completions
Authorization: Bearer <api-key>
Content-Type: application/json

{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "你是一个代码助手"},
    {"role": "user", "content": "解释一下什么是闭包"}
  ],
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": false
}
```

响应格式：

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "gpt-4o",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "闭包是指..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 150,
    "total_tokens": 175
  }
}
```

### /v1/embeddings

嵌入生成接口：

```http
POST /v1/embeddings
Content-Type: application/json

{
  "model": "text-embedding-3-small",
  "input": "向量数据库的工作原理"
}
```

响应：

```json
{
  "object": "list",
  "data": [{
    "object": "embedding",
    "index": 0,
    "embedding": [0.12, -0.34, 0.89, ...]
  }],
  "model": "text-embedding-3-small",
  "usage": {"prompt_tokens": 8, "total_tokens": 8}
}
```

## 流式格式（SSE with delta）

当 `stream: true` 时，响应变为 SSE 格式，每个数据块只包含增量内容：

```
data: {"id":"chatcmpl-abc","choices":[{"delta":{"role":"assistant"},"index":0}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"闭"},"index":0}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"包"},"index":0}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{},"finish_reason":"stop","index":0}]}

data: [DONE]
```

`delta` 字段只包含新增内容，客户端将所有 `delta.content` 拼接起来即得到完整回答。

## 支持 OpenAI 兼容格式的工具

| 工具 | 类型 | 说明 |
|------|------|------|
| vLLM | 本地推理 | 高性能推理框架，完整兼容 OpenAI API |
| Ollama | 本地推理 | 易用的本地模型管理工具 |
| LiteLLM | 代理层 | 统一多个 LLM 提供商的接口 |
| LocalAI | 本地推理 | 支持多种模型格式 |
| Xinference | 本地推理 | 支持分布式部署 |
| Azure OpenAI | 云服务 | 微软托管的 OpenAI 模型 |
| Groq | 云服务 | 高速推理云服务 |

只需修改 `base_url` 和 `api_key`，即可在这些服务之间切换：

```python
from openai import OpenAI

# 切换到本地 Ollama
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"  # Ollama 不需要真实 key
)

# 切换到 vLLM
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="vllm"
)

# 代码完全相同，只改配置
response = client.chat.completions.create(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": "你好"}]
)
```

## Delphi 如何利用 OpenAI 兼容 API

Delphi 将 LLM 调用层设计为可配置的，通过 OpenAI 兼容接口实现模型无关性：

```
用户配置
  base_url: http://localhost:11434/v1  ← 可以是任何兼容服务
  model: qwen2.5:7b                    ← 可以是任何模型名
  api_key: (可选)

Delphi 核心代码
  使用标准 OpenAI SDK 调用
  无需为不同模型编写不同代码
```

这意味着用户可以根据自己的硬件条件选择合适的模型：低配机器用小模型，高配机器用大模型，甚至可以接入云端 API——Delphi 的代码无需任何修改。

嵌入模型同样通过 `/v1/embeddings` 接口调用，支持 Ollama 托管的 BGE-M3 或其他兼容模型。

## 延伸阅读

- [Server-Sent Events (SSE)](./sse.md) — 流式输出的传输协议
- [大语言模型 (LLM)](./llm.md) — LLM 的工作原理
- [向量嵌入 (Embedding)](./embedding.md) — 嵌入接口的使用
