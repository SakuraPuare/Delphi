# Qdrant 向量数据库

Qdrant（读作 "quadrant"）是一款用 Rust 编写的开源向量数据库，专为高性能相似度搜索而设计。它不仅支持纯向量检索，还提供强大的结构化过滤能力，是构建 RAG 系统、语义搜索和推荐引擎的主流选择之一。

## 什么是向量数据库

传统数据库按精确值匹配查询（`WHERE id = 42`）。向量数据库解决的是另一类问题：**给定一个查询向量，找出数据库中语义最相近的向量**。

```
查询: "如何配置 Nginx 反向代理？"
  │
  ▼ Embedding 模型
查询向量: [0.12, -0.87, 0.34, ..., 0.56]  (1536 维)
  │
  ▼ 近似最近邻搜索
结果:
  #1 相似度 0.94 → "Nginx 配置反向代理教程"
  #2 相似度 0.91 → "upstream 负载均衡设置"
  #3 相似度 0.88 → "proxy_pass 指令详解"
```

## 核心架构

### Collection（集合）

Collection 是 Qdrant 的顶层数据组织单元，类似关系数据库中的"表"。每个 Collection 有固定的向量维度和距离度量方式。

```
Qdrant 实例
├── Collection: documents          ← 文档向量集合
│   ├── vector_size: 1536
│   └── distance: Cosine
├── Collection: images
│   ├── vector_size: 512
│   └── distance: Dot
└── Collection: products
    ├── vector_size: 768
    └── distance: Euclid
```

### Point（点）

Point 是 Collection 中的基本数据单元，由三部分组成：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "vector": [0.12, -0.87, 0.34, "...共 1536 个浮点数"],
  "payload": {
    "source": "nginx-guide.pdf",
    "page": 12,
    "chunk_index": 3,
    "text": "要配置反向代理，在 server 块中添加 proxy_pass 指令...",
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

- `id`：唯一标识符，支持 UUID 或无符号整数
- `vector`：浮点数数组，维度必须与 Collection 定义一致
- `payload`：任意 JSON 元数据，用于过滤和结果展示

### Payload（载荷）

Payload 是附加在每个 Point 上的结构化元数据。Qdrant 支持对 Payload 字段建立索引，实现高效的混合查询（向量相似度 + 结构化过滤）。

## 索引类型与距离度量

### 向量索引：HNSW

Qdrant 默认使用 HNSW（Hierarchical Navigable Small World）算法构建向量索引，这是目前近似最近邻搜索的最优算法之一：

```
HNSW 分层结构：
层 2（稀疏）:  A ─────────────── E
层 1（中等）:  A ──── C ──── E ──── G
层 0（密集）:  A ─ B ─ C ─ D ─ E ─ F ─ G ─ H

查询时从顶层快速定位区域，逐层细化，复杂度 O(log n)
```

关键参数：
- `m`：每个节点的最大连接数（默认 16，越大精度越高但内存占用增加）
- `ef_construct`：构建时的搜索宽度（默认 100，影响索引质量）

### 距离度量

| 度量 | 公式 | 适用场景 |
|------|------|----------|
| Cosine | `1 - cos(a,b)` | 文本语义相似度（最常用） |
| Dot Product | `-a·b` | 归一化向量，速度最快 |
| Euclidean | `‖a-b‖₂` | 图像特征、坐标距离 |
| Manhattan | `‖a-b‖₁` | 稀疏向量 |

### Payload 索引

对频繁用于过滤的字段建立索引可大幅提升查询性能：

```http
PUT /collections/documents/index
{
  "field_name": "source",
  "field_schema": "keyword"
}
```

支持的索引类型：`keyword`、`integer`、`float`、`bool`、`datetime`、`text`（全文索引）

## 过滤与混合查询

Qdrant 的过滤器在向量搜索阶段生效（而非搜索后过滤），性能极高：

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

results = client.search(
    collection_name="documents",
    query_vector=query_embedding,
    query_filter=Filter(
        must=[
            FieldCondition(key="source", match=MatchValue(value="manual.pdf")),
            FieldCondition(key="page", range=Range(gte=10, lte=50)),
        ]
    ),
    limit=5,
)
```

过滤条件支持 `must`（AND）、`should`（OR）、`must_not`（NOT）的任意嵌套组合。

## API 接口

### REST API

```bash
# 创建 Collection
curl -X PUT http://localhost:6333/collections/documents \
  -H 'Content-Type: application/json' \
  -d '{"vectors": {"size": 1536, "distance": "Cosine"}}'

# 插入 Points
curl -X PUT http://localhost:6333/collections/documents/points \
  -H 'Content-Type: application/json' \
  -d '{"points": [{"id": 1, "vector": [...], "payload": {"text": "..."}}]}'

# 搜索
curl -X POST http://localhost:6333/collections/documents/points/search \
  -H 'Content-Type: application/json' \
  -d '{"vector": [...], "limit": 5}'
```

### gRPC 接口

Qdrant 同时提供 gRPC 接口（默认端口 6334），适合对延迟敏感的高频调用场景，性能比 REST 高约 30%。

### Python 客户端

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(host="localhost", port=6333)

# 创建集合
client.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

# 批量插入
client.upsert(
    collection_name="documents",
    points=[
        PointStruct(id=i, vector=vec, payload={"text": text})
        for i, (vec, text) in enumerate(zip(vectors, texts))
    ],
)
```

## 部署方式

### Docker 单节点（推荐用于 Delphi）

```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"   # REST API
      - "6334:6334"   # gRPC
    volumes:
      - qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

volumes:
  qdrant_storage:
```

### 分布式集群

Qdrant 支持 Raft 共识协议的分布式部署，通过 Sharding 和 Replication 实现水平扩展：

```
集群架构（3 节点）：
Node 1: Shard 0 (primary) + Shard 1 (replica)
Node 2: Shard 1 (primary) + Shard 2 (replica)
Node 3: Shard 2 (primary) + Shard 0 (replica)
```

### 内存模式（测试用）

```python
client = QdrantClient(":memory:")  # 数据不持久化，适合单元测试
```

## 性能特性

- **写入**：支持批量 upsert，建议每批 100-1000 条
- **查询延迟**：百万级向量 P99 延迟 < 10ms（HNSW 索引）
- **内存占用**：1M 条 1536 维 float32 向量 ≈ 6GB（可用量化压缩至 1.5GB）
- **磁盘存储**：支持 mmap，超出内存的向量自动换页到磁盘

## Delphi 如何使用 Qdrant

### Collection 设计

Delphi 在 Qdrant 中维护一个核心 Collection 用于存储文档片段的向量表示：

```
Collection: delphi_documents
├── vector_size: 与 Embedding 模型输出维度一致
├── distance: Cosine
└── payload schema:
    ├── text: string          ← 原始文本片段
    ├── source: keyword       ← 来源文件路径（建索引）
    ├── doc_id: keyword       ← 文档唯一 ID（建索引）
    ├── chunk_index: integer  ← 片段在文档中的序号
    └── metadata: object      ← 其他元数据（标题、作者等）
```

### 检索策略

Delphi 利用 Qdrant 的混合查询能力，在语义相似度搜索的同时支持按来源文件过滤：

```
用户查询 + 可选的文件范围过滤
         │
         ▼
  Embedding 模型生成查询向量
         │
         ▼
  Qdrant 向量搜索（含 payload 过滤）
         │
         ▼
  返回 Top-K 相关片段 + 原始文本
         │
         ▼
  LlamaIndex 组装上下文 → vLLM 生成回答
```
