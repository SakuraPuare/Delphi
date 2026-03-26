# LlamaIndex RAG 框架

LlamaIndex（原名 GPT Index）是专为构建 LLM 应用而设计的数据框架，核心定位是将私有数据与大语言模型连接起来。在 RAG（Retrieval-Augmented Generation，检索增强生成）领域，LlamaIndex 提供了从数据摄入、索引构建到查询编排的完整工具链。

## 什么是 RAG

RAG 解决的是 LLM 的知识局限性问题：模型训练数据有截止日期，且无法感知私有/内部知识。

```
纯 LLM 方式：
用户问题 ──▶ LLM ──▶ 回答（可能幻觉或过时）

RAG 方式：
用户问题 ──▶ 检索器 ──▶ 相关文档片段 ──┐
                                      ├──▶ LLM ──▶ 基于事实的回答
用户问题 ──────────────────────────────┘
```

LlamaIndex 提供了构建 RAG 管道所需的全部抽象层。

## 核心抽象

### Document（文档）

Document 是数据摄入的起点，代表一个原始数据单元（一个 PDF 文件、一个网页、一段数据库记录等）：

```python
from llama_index.core import Document

doc = Document(
    text="Nginx 是一款高性能的 HTTP 服务器...",
    metadata={
        "source": "nginx-guide.pdf",
        "author": "张三",
        "created_at": "2024-01-01",
    },
)
```

LlamaIndex 内置了数十种 Reader（数据加载器），可直接从 PDF、Word、Notion、数据库等来源创建 Document。

### Node（节点）

Node 是 Document 经过切分（chunking）后的最小处理单元，是实际存入向量数据库的对象：

```
Document（整篇 PDF）
    │
    ▼ NodeParser（文本切分）
    ├── Node #0: "第一章 安装..." (chunk_size=512)
    ├── Node #1: "配置文件位于..." (chunk_size=512)
    └── Node #2: "常见问题排查..." (chunk_size=512)
```

每个 Node 保留对父 Document 的引用，并携带位置信息（`start_char_idx`、`end_char_idx`）。

### Index（索引）

Index 是 LlamaIndex 的核心数据结构，负责将 Node 组织成可检索的形式。最常用的是 `VectorStoreIndex`：

```python
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore

vector_store = QdrantVectorStore(client=qdrant_client, collection_name="docs")
index = VectorStoreIndex.from_documents(
    documents,
    vector_store=vector_store,
)
```

构建过程：
```
Documents
   │
   ▼ NodeParser（切分）
  Nodes
   │
   ▼ EmbeddingModel（向量化）
  Vectors
   │
   ▼ VectorStore（存储）
  Index（可检索）
```

其他索引类型：
- `SummaryIndex`：为每个文档生成摘要，适合长文档问答
- `KnowledgeGraphIndex`：构建知识图谱
- `KeywordTableIndex`：基于关键词的倒排索引

### Retriever（检索器）

Retriever 从 Index 中根据查询找出最相关的 Node：

```python
retriever = index.as_retriever(similarity_top_k=5)
nodes = retriever.retrieve("如何配置 SSL 证书？")
# 返回 5 个最相关的 Node 对象，含相似度分数
```

高级检索策略：
- `BM25Retriever`：基于关键词的稀疏检索
- `HybridRetriever`：稠密向量 + 稀疏检索融合（RRF 重排）
- `AutoMergingRetriever`：检索子节点后自动合并为父节点上下文

### QueryEngine（查询引擎）

QueryEngine 是端到端的问答接口，封装了"检索 → 组装 prompt → LLM 生成"的完整流程：

```python
query_engine = index.as_query_engine(
    llm=llm,
    similarity_top_k=5,
    streaming=True,
)
response = query_engine.query("Nginx 如何配置负载均衡？")
print(response)
```

内部执行流程：
```
用户查询
   │
   ▼ Retriever
相关 Nodes（含原文）
   │
   ▼ ResponseSynthesizer（组装 prompt）
"根据以下资料回答问题：\n[Node 1]\n[Node 2]\n...\n问题：..."
   │
   ▼ LLM
最终回答
```

## 内置集成

LlamaIndex 拥有庞大的集成生态：

**向量存储**：Qdrant、Pinecone、Weaviate、Chroma、Milvus、pgvector、Redis 等 20+

**LLM**：OpenAI、Anthropic、Cohere、本地 Ollama、vLLM（通过 OpenAI 兼容接口）等

**Embedding 模型**：OpenAI、HuggingFace（本地）、Cohere、Jina 等

**数据加载器**：PDF、Word、Excel、Notion、Confluence、GitHub、数据库等 100+

```python
# 使用本地 HuggingFace Embedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-m3")

# 使用 vLLM 作为 LLM 后端
from llama_index.llms.openai import OpenAI

llm = OpenAI(
    model="Qwen2.5-7B-Instruct",
    api_base="http://localhost:8000/v1",
    api_key="dummy",
)
```

## 与 LangChain 的对比

LlamaIndex 和 LangChain 是 RAG 领域最常被比较的两个框架：

| 维度 | LlamaIndex | LangChain |
|------|-----------|-----------|
| 核心定位 | 数据索引与检索 | 通用 LLM 应用编排 |
| RAG 支持 | 深度优化，开箱即用 | 需要手动组装 |
| 学习曲线 | 较平缓（RAG 场景） | 较陡（概念更多） |
| 灵活性 | 中（RAG 场景最优） | 高（适合复杂 Agent） |
| 数据连接器 | 100+ 专用 Reader | 通用 Loader |
| Agent 支持 | 支持，但非重点 | 强项 |
| 社区生态 | 专注 RAG/搜索 | 更广泛 |

**选择建议**：
- 主要需求是 RAG、知识库问答 → LlamaIndex
- 需要复杂 Agent、工具调用编排 → LangChain 或 LangGraph

## 构建基础 RAG 管道

以下是一个完整的最小化 RAG 示例：

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# 1. 配置全局设置
Settings.llm = OpenAI(
    model="Qwen2.5-7B-Instruct",
    api_base="http://localhost:8000/v1",
    api_key="dummy",
)
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-m3")
Settings.chunk_size = 512
Settings.chunk_overlap = 50

# 2. 加载文档
documents = SimpleDirectoryReader("./docs").load_data()

# 3. 构建索引（自动切分、向量化、存储）
index = VectorStoreIndex.from_documents(documents)

# 4. 创建查询引擎
query_engine = index.as_query_engine(similarity_top_k=5)

# 5. 查询
response = query_engine.query("如何配置 HTTPS？")
print(response)

# 查看引用来源
for node in response.source_nodes:
    print(f"来源: {node.metadata['file_name']}, 相似度: {node.score:.3f}")
```

## Delphi 如何使用 LlamaIndex

LlamaIndex 是 Delphi 的核心编排层，负责连接所有组件：

```
文档上传
   │
   ▼ SimpleDirectoryReader / 自定义 Reader
  Documents
   │
   ▼ SentenceSplitter（按句子边界切分）
  Nodes
   │
   ▼ HuggingFace Embedding（本地运行）
  Vectors
   │
   ▼ QdrantVectorStore
  持久化存储
   │
   ▼（查询时）
  VectorIndexRetriever（Top-K 检索 + payload 过滤）
   │
   ▼ CompactAndRefine ResponseSynthesizer
  组装 prompt
   │
   ▼ vLLM（OpenAI 兼容接口）
  流式回答
```

Delphi 的具体使用方式：

- **索引构建**：文档上传后异步触发，使用 `IngestionPipeline` 支持增量更新，避免重复向量化
- **检索配置**：`similarity_top_k=8`，结合 Qdrant payload 过滤实现按知识库范围检索
- **上下文压缩**：使用 `LongContextReorder` 将最相关片段放置在 prompt 首尾，缓解 LLM 中间遗忘问题
- **引用溯源**：每次回答附带 `source_nodes`，前端展示原文来源和相似度分数
