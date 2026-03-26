# 向量数据库

## 选型：Qdrant

| 属性 | 值 |
|------|-----|
| 实现语言 | Rust |
| 部署方式 | 单二进制 / Docker |
| 百万级数据 P95 延迟 | < 30ms |
| 元数据过滤 | 丰富（数值、文本、地理等） |
| 持久化 | 磁盘持久化 + mmap |

### 为什么选 Qdrant 而不是 Milvus

| 维度 | Qdrant | Milvus |
|------|--------|--------|
| 部署复杂度 | 单二进制，零依赖 | 需要 etcd + MinIO（Standalone 模式） |
| 百万级性能 | 优秀 | 优秀 |
| 运维成本 | 极低 | 中等 |
| 原生 Sparse 向量 | 不支持 | 2.5 版本支持 |
| 元数据过滤 | 丰富且高效 | 支持但相对基础 |

Delphi 的数据规模（百万级 Chunk）在 Qdrant 单节点的舒适区内。如果后续数据量增长到千万级且需要原生 Sparse 向量支持，可迁移到 Milvus。

### 混合检索方案

由于 Qdrant 不原生支持 Sparse 向量检索，混合检索通过以下方式实现：

```
BGE-M3 → Dense 向量 → Qdrant 向量检索（语义匹配）
                              +
       → 关键词 → Qdrant Payload 全文搜索（精确匹配）
                              ↓
                     RRF 分数融合 → 排序
```

## 数据模型

### Collection 设计

```
delphi_chunks
├── vector: float[1024]        # BGE-M3 Dense embedding
├── payload:
│   ├── content: string        # Chunk 原文
│   ├── chunk_type: string     # code / doc / media_transcript
│   ├── file_path: string      # 源文件路径
│   ├── language: string       # 编程语言
│   ├── namespace: string      # 命名空间/包名
│   ├── class_name: string     # 所属类
│   ├── symbol: string         # 函数/方法签名
│   ├── heading_path: string   # 文档标题层级路径
│   ├── source_hash: string    # 源文件 SHA-256
│   ├── project: string        # 所属项目（支持多项目）
│   └── created_at: datetime   # 入库时间
```

### 索引配置

```yaml
# Qdrant collection 配置
vectors:
  size: 1024
  distance: Cosine

# Payload 索引（加速过滤）
payload_indexes:
  - field: file_path
    type: text
  - field: language
    type: keyword
  - field: chunk_type
    type: keyword
  - field: project
    type: keyword
  - field: symbol
    type: text
```

## 容量估算

以 100 万 Chunk 为例：

| 项目 | 大小 |
|------|------|
| 向量数据（1024 × float32 × 1M） | ~4GB |
| HNSW 索引 | ~8GB |
| Payload 数据 | ~2GB |
| 总计 | ~14GB |

单机 64GB 内存可轻松容纳。开启 mmap 模式后，内存压力进一步降低。
