# RAG 编排

## 渐进式架构

Delphi 的 RAG 架构采用渐进式设计，从简单到复杂分三个阶段：

## Phase 1：线性 RAG

最基础的检索-生成流程，MVP 阶段使用：

```
用户查询
   ↓
Query 改写（可选：扩展同义词、补全缩写）
   ↓
BGE-M3 Embedding → Qdrant 向量检索
   ↓
Top-K 候选 Chunk（默认 K=20）
   ↓
BGE-Reranker 精排 → Top-N（默认 N=5）
   ↓
Prompt 组装（System Prompt + 检索上下文 + 用户查询）
   ↓
vLLM 生成 → 流式输出
```

### Query 改写

对用户原始查询进行预处理，提升检索召回率：

- **关键词提取**：从自然语言问题中提取代码符号（函数名、类名）
- **同义扩展**：如 `规划模块` → `planning module`
- **HyDE**（Hypothetical Document Embedding）：让 LLM 先生成一个假设性回答，用回答的 embedding 去检索

### Prompt 模板

```
你是一个代码知识库助手。根据以下检索到的上下文回答用户问题。
如果上下文中没有相关信息，请明确说明。回答时引用来源文件路径。

## 检索上下文

{context}

## 用户问题

{query}
```

## Phase 2：多路检索 + 意图路由

根据查询意图选择不同的检索策略：

```
用户查询
   ↓
意图分类器（LLM / 规则）
   ├─ 代码查询 → AST 元数据过滤 + 向量检索
   ├─ 文档查询 → 标准向量检索
   ├─ API 查询 → 函数签名精确匹配 + 向量检索
   └─ 架构查询 → 构建文件检索 + 代码检索
   ↓
结果融合（RRF / 加权合并）
   ↓
Reranker → LLM 生成
```

### 元数据过滤

利用 Qdrant 的 payload 过滤能力，在向量检索前缩小搜索范围：

```python
# 示例：只在 planning 模块的 C++ 文件中搜索
filter = {
    "must": [
        {"key": "language", "match": {"value": "cpp"}},
        {"key": "file_path", "match": {"text": "modules/planning"}}
    ]
}
```

## Phase 3：Agentic RAG

引入 LangGraph 的 Plan-Execute-Reflect 模式：

```
用户查询
   ↓
Planner（LLM）→ 生成执行计划（DAG）
   ↓
Executor → 按计划调用工具：
   ├─ vector_search(query, filters)
   ├─ keyword_search(symbol_name)
   ├─ get_file(path)
   └─ get_dependencies(target)
   ↓
Reflector（LLM）→ 审查结果是否充分
   ├─ 充分 → 生成最终回答
   └─ 不充分 → 生成补充查询 → 回到 Executor
```

这一阶段仅在 Phase 1/2 无法满足复杂多跳查询时引入。

## 框架选择

使用 LlamaIndex 作为 RAG 编排框架：

- 内置 QueryEngine、Retriever、Reranker 等 RAG 原语
- 支持多种向量数据库后端
- 与 vLLM 的 OpenAI 兼容 API 无缝对接
- Phase 3 可通过 LlamaIndex Agent 或切换到 LangGraph 实现
