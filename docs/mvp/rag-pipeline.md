# 功能：基础 RAG Pipeline

## 功能描述

用户通过 API 输入自然语言问题，系统执行以下操作：

1. 将问题转换为 [Embedding](../concepts/core/embedding.md) 向量
2. 在 Qdrant 中检索最相关的 Top-K [Chunk](../concepts/data/chunking.md)
3. 将检索结果与问题组装为 Prompt
4. 调用 [LLM](../concepts/core/llm.md) 生成回答
5. 以 SSE 流式返回回答，并附带来源引用

---

## 详细需求列表

### P0（必须实现）

1. 接受自然语言问题，返回基于知识库内容的回答
2. 检索时支持指定目标 collection（对应某个已导入的仓库或文档目录）
3. 默认检索 Top-5 Chunk，`top_k` 参数可配置（范围 1-20）
4. 使用 SSE（Server-Sent Events）流式返回生成内容
5. 回答结束后，在同一 SSE 流中返回来源引用列表
6. 当检索结果为空时，返回明确提示，不调用 LLM

### P1（应该实现）

7. 支持 `collection_ids` 数组，跨多个 collection 检索（结果合并后重排）
8. 检索结果按相似度分数过滤，低于阈值（默认 0.5）的 Chunk 丢弃
9. Prompt 中的上下文总长度不超过[上下文窗口](../concepts/core/context-window.md)限制，超出时截断低分 Chunk
10. 支持非流式模式（`stream=false`），一次性返回完整回答

### P2（可以实现）

11. 支持 `system_prompt` 参数，允许用户自定义系统提示词
12. 返回每个 Chunk 的相似度分数，便于调试

---

## 输入/输出规格

### 请求

```http
POST /api/v1/query
Content-Type: application/json

{
  "question": "这个项目如何处理用户认证？",
  "collection_ids": ["repo_abc123"],  // 可选，默认查询所有 collection
  "top_k": 5,                         // 可选，默认 5
  "stream": true,                     // 可选，默认 true
  "score_threshold": 0.5              // 可选，默认 0.5
}
```

### 流式响应（SSE）

```
Content-Type: text/event-stream

data: {"type": "token", "content": "该项目"}

data: {"type": "token", "content": "使用 JWT"}

data: {"type": "token", "content": " 进行用户认证..."}

data: {"type": "sources", "sources": [
  {
    "file_path": "src/auth/jwt.py",
    "start_line": 42,
    "end_line": 78,
    "score": 0.91,
    "title": null
  },
  {
    "file_path": "docs/auth.md",
    "start_line": null,
    "end_line": null,
    "score": 0.83,
    "title": "认证机制 > JWT 配置"
  }
]}

data: {"type": "done"}
```

### 非流式响应

```json
{
  "answer": "该项目使用 JWT 进行用户认证...",
  "sources": [...],
  "usage": {
    "prompt_tokens": 1240,
    "completion_tokens": 180
  }
}
```

---

## 检索流程

```
用户问题
    │
    ▼
[1] 参数校验
    │  question 非空，top_k 范围检查
    ▼
[2] Query Embedding
    │  调用 BGE-M3，将问题转为向量
    ▼
[3] Qdrant 向量检索
    │  search(collection, query_vector, limit=top_k*2)
    │  返回候选 Chunk 列表（含 score）
    ▼
[4] 分数过滤
    │  丢弃 score < score_threshold 的结果
    │  取前 top_k 个
    ▼
[5] 上下文长度检查
    │  累计 token 数，超出窗口限制时截断末尾 Chunk
    ▼
[6] Prompt 组装
    │  填入 Prompt 模板（见下节）
    ▼
[7] LLM 生成（流式）
    │  调用 vLLM / OpenAI 兼容接口
    │  stream=True
    ▼
[8] SSE 推送
    │  逐 token 推送 {"type": "token", "content": "..."}
    │  生成完毕后推送 {"type": "sources", ...}
    │  最后推送 {"type": "done"}
```

---

## Prompt 模板

```
你是一个代码与文档问答助手。请根据以下检索到的上下文内容回答用户的问题。

规则：
- 只基于提供的上下文回答，不要编造信息
- 如果上下文中没有足够信息，明确说明"根据现有文档，无法回答该问题"
- 回答时引用具体的文件或章节名称
- 代码示例使用代码块格式

---上下文开始---
[来源: {file_path}, 行 {start_line}-{end_line}]
{chunk_content}

[来源: {file_path}, 标题: {title}]
{chunk_content}

（重复，共 {top_k} 条）
---上下文结束---

用户问题：{question}

请回答：
```

---

## 流式输出（SSE）规格

- 端点：`POST /api/v1/query`，请求头需包含 `Accept: text/event-stream`
- 每条 SSE 消息格式：`data: <JSON>\n\n`
- 消息类型：
  - `token`：LLM 生成的文本片段，`content` 字段为字符串
  - `sources`：来源引用列表，在所有 token 推送完毕后发送
  - `error`：错误信息，`message` 字段描述错误
  - `done`：流结束标志
- 客户端应在收到 `done` 或连接关闭时停止读取

---

## 引用来源返回格式

每条来源包含以下字段：

```json
{
  "file_path": "src/auth/jwt.py",   // 相对于仓库根目录或文档目录
  "start_line": 42,                  // 代码文件专用，null 表示不适用
  "end_line": 78,
  "title": null,                     // 文档文件专用，标题路径
  "score": 0.91,                     // 相似度分数 [0, 1]
  "collection_id": "repo_abc123"     // 来源 collection
}
```

---

## 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| 检索结果为空（或全部低于阈值） | 不调用 LLM，直接返回 `{"type": "error", "message": "未找到相关内容，请尝试换一种提问方式"}` |
| LLM 服务超时（默认 30s） | 推送 `{"type": "error", "message": "LLM 响应超时，请稍后重试"}`，关闭 SSE 连接 |
| LLM 服务不可用 | 返回 503，`{"detail": "LLM 服务暂不可用"}` |
| Embedding 服务不可用 | 返回 503，`{"detail": "Embedding 服务暂不可用"}` |
| Qdrant 不可用 | 返回 503，`{"detail": "向量数据库暂不可用"}` |
| 问题为空字符串 | 返回 400，`{"detail": "question 不能为空"}` |

---

## 相关概念

- [RAG（检索增强生成）](../concepts/core/rag.md) — RAG 架构原理
- [Embedding（向量嵌入）](../concepts/core/embedding.md) — 向量生成与相似度检索
- [Prompt Engineering](../concepts/core/prompt-engineering.md) — Prompt 设计策略
- [上下文窗口](../concepts/core/context-window.md) — Token 限制与截断策略
- [LLM（大语言模型）](../concepts/core/llm.md) — 模型推理与接口规范
- [向量数据库](../concepts/core/vector-database.md) — Qdrant 检索配置
