# RAG 框架对比

本文对主流 RAG 框架进行横向对比，帮助你理解 Delphi 选择 LlamaIndex 的原因。

## 框架概览

| 框架 | 定位 | 主要语言 | 首发年份 |
|------|------|----------|----------|
| LlamaIndex | 数据框架，专注 RAG 与知识检索 | Python | 2022 |
| LangChain | 通用 LLM 应用编排框架 | Python / JS | 2022 |
| Haystack | 企业级 NLP / RAG 流水线 | Python | 2020 |
| RAGFlow | 开箱即用的 RAG 平台（含 UI） | Python | 2024 |
| Dify | 低代码 LLM 应用平台 | Python / TS | 2023 |

---

## 多维度对比

| 维度 | LlamaIndex | LangChain | Haystack | RAGFlow | Dify |
|------|-----------|-----------|----------|---------|------|
| 抽象层级 | 中（数据为核心） | 高（链式编排） | 中（Pipeline 组件） | 低（平台化） | 极低（可视化） |
| 向量库支持 | 35+ | 50+ | 20+ | 内置 Infinity | 内置 Weaviate |
| LLM 集成 | OpenAI / Ollama / vLLM 等 | 同左，更广 | OpenAI / HF | 内置多模型 | 内置多模型 |
| 代码 RAG 能力 | 原生支持（CodeSplitter） | 需自定义 | 有限 | 无 | 无 |
| 社区活跃度 | ★★★★☆ | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ |
| 学习曲线 | 中等 | 陡峭 | 中等 | 平缓 | 极平缓 |
| 适合场景 | 知识库 / 代码搜索 | 复杂 Agent 流程 | 企业搜索 | 快速原型 | 无代码应用 |

---

## 各框架优劣分析

### LlamaIndex

优势：
- 以"数据索引"为核心抽象，RAG 流程清晰直观
- 内置 `CodeSplitter`，对代码文件的分块与检索有原生支持
- `QueryEngine` / `RetrieverQueryEngine` 分层设计，易于定制
- 与 Qdrant、Weaviate、Milvus 等向量库深度集成

劣势：
- Agent 编排能力弱于 LangChain
- 生态广度不及 LangChain

### LangChain

优势：
- 生态最广，集成数量最多
- LCEL（LangChain Expression Language）支持复杂链式组合
- Agent / Tool 体系成熟

劣势：
- 抽象层次过高，调试困难
- 版本迭代快，API 变动频繁，维护成本高
- RAG 专项能力不如 LlamaIndex 精细

### Haystack

优势：
- Pipeline 组件化设计，适合企业级搜索场景
- 对 Elasticsearch / OpenSearch 支持好

劣势：
- 代码 RAG 支持薄弱
- 社区规模相对较小

### RAGFlow

优势：
- 开箱即用，自带 Web UI
- 文档解析能力强（PDF / 表格）

劣势：
- 可编程性差，难以深度定制
- 不适合嵌入到已有系统

### Dify

优势：
- 可视化拖拽，非技术人员可用
- 快速搭建原型

劣势：
- 代码控制能力极弱
- 不适合需要精细调优的场景

---

## 代码示例对比

以下展示用 LlamaIndex 和 LangChain 实现同一个 RAG 流水线。

### LlamaIndex

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.ollama import Ollama
import qdrant_client

# 初始化向量库
client = qdrant_client.QdrantClient(url="http://localhost:6333")
vector_store = QdrantVectorStore(client=client, collection_name="docs")

# 加载文档并建立索引
documents = SimpleDirectoryReader("./data").load_data()
index = VectorStoreIndex.from_documents(
    documents,
    vector_store=vector_store,
)

# 查询
llm = Ollama(model="qwen2.5:7b")
query_engine = index.as_query_engine(llm=llm, similarity_top_k=5)
response = query_engine.query("Delphi 如何处理代码文件？")
print(response)
```

### LangChain

```python
from langchain_community.vectorstores import Qdrant
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
from langchain_community.document_loaders import DirectoryLoader

# 加载文档
loader = DirectoryLoader("./data")
documents = loader.load()

# 初始化向量库
embeddings = OllamaEmbeddings(model="nomic-embed-text")
vectorstore = Qdrant.from_documents(
    documents,
    embeddings,
    url="http://localhost:6333",
    collection_name="docs",
)

# 查询
llm = Ollama(model="qwen2.5:7b")
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=vectorstore.as_retriever(search_kwargs={"k": 5}),
)
response = qa_chain.run("Delphi 如何处理代码文件？")
print(response)
```

两者功能相近，但 LlamaIndex 的 `VectorStoreIndex` 对索引生命周期管理更清晰，而 LangChain 需要手动管理 embedding 与 vectorstore 的绑定关系。

---

## Delphi 选择 LlamaIndex 的原因

1. 代码感知分块：`CodeSplitter` 按语法树切分，保留函数/类边界，避免语义断裂
2. 索引抽象清晰：`VectorStoreIndex` 与 `Qdrant` 的集成经过充分测试，稳定性好
3. 查询引擎可组合：支持混合检索（向量 + BM25）、重排序、子问题分解等高级策略
4. 维护成本低：API 相对稳定，升级风险小于 LangChain
5. 与 Delphi 架构契合：Delphi 以"知识库索引"为核心，LlamaIndex 的设计哲学完全对齐

如果你的场景需要复杂的多步 Agent 或工具调用，LangChain 或 LlamaIndex 的 `AgentRunner` 都是可选方案。
