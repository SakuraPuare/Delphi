# 向量数据库对比

本文对主流向量数据库进行横向对比，帮助你理解 Delphi 选择 Qdrant 的原因，以及何时应考虑迁移到其他方案。

## 数据库概览

| 数据库 | 定位 | 开源协议 | 实现语言 |
|--------|------|----------|----------|
| Qdrant | 高性能向量搜索引擎 | Apache 2.0 | Rust |
| Milvus | 云原生分布式向量数据库 | Apache 2.0 | Go / C++ |
| ChromaDB | 轻量级嵌入式向量库 | Apache 2.0 | Python |
| Weaviate | 向量搜索 + 知识图谱 | BSD 3-Clause | Go |
| Pinecone | 全托管向量数据库（SaaS） | 闭源 | — |
| pgvector | PostgreSQL 向量扩展 | PostgreSQL License | C |

---

## 多维度对比

| 维度 | Qdrant | Milvus | ChromaDB | Weaviate | Pinecone | pgvector |
|------|--------|--------|----------|----------|----------|----------|
| 部署复杂度 | 低（单二进制） | 高（依赖 etcd/Kafka） | 极低（pip install） | 中 | 无需部署 | 低（PostgreSQL 插件） |
| 百万级 QPS | ~2000 | ~3000 | ~500 | ~1500 | ~2000 | ~300 |
| 千万级 QPS | ~800 | ~2500 | 不推荐 | ~600 | ~1500 | 不推荐 |
| 元数据过滤 | 原生支持，性能优秀 | 支持 | 基础支持 | 支持 | 支持 | 依赖 SQL WHERE |
| 混合检索 | 支持（稀疏+密集） | 支持 | 不支持 | 支持 | 支持 | 需手动实现 |
| 持久化 | 默认持久化 | 默认持久化 | 可选 | 默认持久化 | 云端持久化 | PostgreSQL 持久化 |
| 分布式 | 支持（Raft） | 原生分布式 | 不支持 | 支持 | 全托管 | 不支持 |
| 语言客户端 | Python / Rust / Go / JS | Python / Go / Java | Python / JS | Python / Go / JS | Python / JS | 任意 PostgreSQL 客户端 |

> 注：QPS 数据来自各官方 benchmark 及社区测试，实际性能因硬件、向量维度、索引参数而异。

---

## 部署复杂度详解

### Qdrant（推荐用于 Delphi）

```bash
# Docker 单节点，30 秒启动
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

无外部依赖，配置文件可选，REST + gRPC 双协议，适合本地开发到中等规模生产。

### Milvus

```bash
# 需要 etcd + MinIO + Milvus 三个服务
wget https://github.com/milvus-io/milvus/releases/download/v2.4.0/milvus-standalone-docker-compose.yml
docker compose up -d
```

依赖链长，但分布式能力强，适合千万级以上数据量。

### ChromaDB

```python
import chromadb
client = chromadb.Client()  # 内存模式，零配置
# 或
client = chromadb.PersistentClient(path="./chroma_db")
```

最简单，适合原型开发，不适合生产。

### pgvector

```sql
CREATE EXTENSION vector;
CREATE TABLE items (id bigserial PRIMARY KEY, embedding vector(1536));
CREATE INDEX ON items USING ivfflat (embedding vector_cosine_ops);
```

如果已有 PostgreSQL 基础设施，pgvector 可以零增量运维成本接入，但性能上限较低。

---

## 性能 Benchmark 参考

以下数据基于 1M 条 768 维向量，单节点，HNSW 索引：

| 数据库 | 索引构建时间 | p99 查询延迟 | 内存占用 | Recall@10 |
|--------|-------------|-------------|----------|-----------|
| Qdrant | ~8 min | 4 ms | ~4 GB | 0.97 |
| Milvus | ~12 min | 5 ms | ~6 GB | 0.97 |
| Weaviate | ~15 min | 8 ms | ~5 GB | 0.96 |
| ChromaDB | ~20 min | 15 ms | ~3 GB | 0.95 |
| pgvector | ~25 min | 20 ms | ~4 GB | 0.94 |

---

## 各数据库适用场景

- Qdrant：本地部署、中小规模（百万级）、需要混合检索、对运维复杂度敏感
- Milvus：大规模（千万级以上）、需要水平扩展、有 DevOps 团队支持
- ChromaDB：快速原型、单机开发环境、数据量 < 10 万
- Weaviate：需要知识图谱与向量检索结合的场景
- Pinecone：不想管理基础设施、预算充足、数据可以上云
- pgvector：已有 PostgreSQL、数据量小、希望统一存储层

---

## Delphi 选择 Qdrant 的原因

1. 部署简单：单二进制 / 单容器，无外部依赖，符合 Delphi"本地可部署"的核心定位
2. Rust 实现：内存安全，性能稳定，低延迟
3. 混合检索：原生支持稀疏向量（BM25）与密集向量联合检索，提升代码搜索召回率
4. 元数据过滤：支持对 `repo`、`language`、`file_path` 等字段高效过滤，无需全量扫描
5. LlamaIndex 集成成熟：`QdrantVectorStore` 经过充分测试，API 稳定

---

## 何时考虑迁移到 Milvus

当出现以下情况时，可以评估迁移到 Milvus：

- 单个知识库的向量数量超过 **5000 万条**，Qdrant 单节点内存压力过大
- 需要多副本高可用，且团队有能力维护 Kubernetes 集群
- 需要细粒度的资源隔离（多租户场景）
- 已有 Milvus 运维经验，迁移成本可控

迁移时，LlamaIndex 提供了 `MilvusVectorStore`，接口与 `QdrantVectorStore` 基本一致，切换成本较低。
