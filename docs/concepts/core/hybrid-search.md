# 混合检索 (Hybrid Search)

RAG 系统的核心挑战之一是：如何从知识库中找到真正相关的内容？单一的检索策略往往顾此失彼。混合检索通过结合关键词检索和语义检索，在准确性和召回率之间取得更好的平衡。

## 问题：语义检索并非万能

向量语义检索（Semantic Search）是 RAG 的标配，但它有明显的短板：

```
用户问题: "QueryBuilder 的 addSelect 方法怎么用？"

语义检索结果（可能）:
  1. "如何构建数据库查询" （语义相似，但没有 addSelect）
  2. "ORM 查询示例" （相关，但不精确）
  3. "SQL SELECT 语句" （语义相关，但不是目标方法）

实际需要的文档:
  → TypeORM QueryBuilder.addSelect() 的 API 文档（精确匹配）
```

语义检索擅长理解意图，但对**精确的技术术语、函数名、错误码**等的匹配能力较弱。

## 关键词检索：BM25 / TF-IDF

### TF-IDF

最经典的文本相关性算法，基于词频统计：

- **TF（词频）**：词在文档中出现的频率
- **IDF（逆文档频率）**：词在整个语料库中的稀有程度

```
TF-IDF(词, 文档) = TF(词, 文档) × IDF(词, 语料库)

"addSelect" 在目标文档中出现 5 次（高 TF）
"addSelect" 在整个代码库中只出现 8 次（高 IDF）
→ TF-IDF 分数高，文档被排在前面
```

### BM25（Best Match 25）

BM25 是 TF-IDF 的改进版，是现代搜索引擎的基础算法：

```
BM25(q, d) = Σ IDF(qi) × [tf(qi,d) × (k1+1)] / [tf(qi,d) + k1×(1 - b + b×|d|/avgdl)]
```

其中：
- `k1`（通常 1.2~2.0）：控制词频饱和度，避免高频词权重无限增长
- `b`（通常 0.75）：文档长度归一化因子
- `|d|/avgdl`：文档长度与平均长度之比

**BM25 的优势：**
- 对精确关键词匹配极其敏感
- 对函数名、类名、错误码等技术术语效果好
- 计算速度快，无需 GPU

**BM25 的劣势：**
- 无法理解同义词（`get` vs `fetch` vs `retrieve`）
- 无法处理语义相似但用词不同的查询
- 对拼写错误敏感

## 语义检索：向量搜索

将文本转换为高维向量，通过余弦相似度或点积衡量语义距离：

```
文本 → 嵌入模型 → 向量 [0.23, -0.45, 0.67, ...]（768 或 1024 维）

查询向量与文档向量的余弦相似度：
cos(θ) = (A·B) / (|A|×|B|)
```

**语义检索的优势：**
- 理解同义词和近义表达
- 跨语言检索（中文问题匹配英文文档）
- 对拼写错误有一定容忍度
- 能捕捉概念层面的相关性

**语义检索的劣势：**
- 对精确术语匹配不如关键词检索
- 嵌入模型可能将不相关但语义相似的内容混淆
- 需要 GPU 加速，计算成本较高

## 混合检索：取长补短

混合检索同时运行两种检索，然后融合结果：

```
用户查询: "addSelect 方法的参数类型"
         ↓
    ┌────────────────────────────────┐
    │                                │
    ▼                                ▼
BM25 检索                      向量语义检索
（精确匹配 "addSelect"）        （理解"参数类型"的语义）
    │                                │
    ▼                                ▼
BM25 结果列表                  向量结果列表
[doc_A: rank 1]               [doc_B: rank 1]
[doc_C: rank 2]               [doc_A: rank 2]
[doc_B: rank 3]               [doc_D: rank 3]
    │                                │
    └──────────┬─────────────────────┘
               ▼
          分数融合算法
               ↓
        最终排序结果
[doc_A: 综合最高]
[doc_B: 综合第二]
...
```

## 分数融合方法

### 加权求和（Weighted Sum）

```python
final_score = α × bm25_score + (1-α) × vector_score
```

问题：两种分数的量纲不同，BM25 分数可能是 0~20，向量相似度是 0~1，直接相加需要归一化，且权重 α 难以调优。

### RRF（Reciprocal Rank Fusion）

RRF 是目前最推荐的融合方法，只使用排名而非原始分数，天然解决了量纲问题：

```python
RRF_score(doc) = Σ 1 / (k + rank_i(doc))
```

其中 `k`（通常为 60）是平滑参数，防止排名第 1 的文档权重过大。

**具体示例：**

```
doc_A 在 BM25 中排名第 1，在向量检索中排名第 2：
RRF(doc_A) = 1/(60+1) + 1/(60+2) = 0.01639 + 0.01613 = 0.03252

doc_B 在 BM25 中排名第 3，在向量检索中排名第 1：
RRF(doc_B) = 1/(60+3) + 1/(60+1) = 0.01587 + 0.01639 = 0.03226

doc_C 只出现在 BM25 中，排名第 2：
RRF(doc_C) = 1/(60+2) + 0 = 0.01613

最终排序: doc_A > doc_B > doc_C
```

RRF 的优势：
- 无需调参（k=60 在大多数场景表现良好）
- 对异常高分不敏感
- 实现简单，效果稳定

## 代码符号检索示例

以 Delphi 检索代码库为例，混合检索的优势尤为明显：

**场景：用户询问 "怎么处理数据库连接超时错误"**

```
BM25 检索（关键词匹配）:
  → "ConnectionTimeoutError" 相关文档（精确匹配错误类名）
  → "timeout" 配置项文档

向量检索（语义匹配）:
  → "数据库连接池配置" 文档（语义相关）
  → "重试机制实现" 文档（解决方案相关）
  → "网络错误处理" 文档（概念相关）

混合结果（RRF 融合）:
  1. "ConnectionTimeoutError 处理指南"（两种检索都命中）
  2. "数据库连接池配置"（语义高度相关）
  3. "重试机制实现"（解决方案相关）
  4. "timeout 配置项"（关键词匹配）
```

## Delphi 的混合检索实现

Delphi 使用 **BGE-M3** 作为嵌入模型，**Qdrant** 作为向量数据库，实现混合检索。

### BGE-M3 的特殊能力

BGE-M3（BAAI General Embedding - Multi-Functionality, Multi-Linguality, Multi-Granularity）是一个特殊的嵌入模型，单模型同时支持三种检索模式：

```
BGE-M3
  ├── Dense Retrieval（稠密向量，用于语义检索）
  ├── Sparse Retrieval（稀疏向量，类似 BM25 的词汇检索）
  └── ColBERT（多向量，细粒度交互）
```

这意味着 Delphi 可以用同一个模型完成混合检索，无需额外部署 BM25 引擎。

### Qdrant 的混合检索支持

```python
# Delphi 内部检索逻辑（简化示意）
from qdrant_client import QdrantClient
from qdrant_client.models import SparseVector, NamedSparseVector, NamedVector

client = QdrantClient("localhost", port=6333)

# 同时使用稠密向量和稀疏向量检索
results = client.query_points(
    collection_name="delphi_docs",
    prefetch=[
        # 稠密向量检索（语义）
        models.Prefetch(query=dense_vector, using="dense", limit=20),
        # 稀疏向量检索（关键词）
        models.Prefetch(query=sparse_vector, using="sparse", limit=20),
    ],
    # RRF 融合
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=5,
)
```

### 配置混合检索

```yaml
# config.yaml
retrieval:
  mode: hybrid              # dense | sparse | hybrid
  top_k: 5                  # 最终返回结果数
  prefetch_k: 20            # 每路检索的候选数
  fusion: rrf               # rrf | weighted_sum
  rrf_k: 60                 # RRF 平滑参数

embedding:
  model: BAAI/bge-m3
  device: cuda              # 或 cpu
```

## 延伸阅读

- [大语言模型基础](./llm.md)
- [分词与 Token](./tokenization.md)
- [上下文窗口](./context-window.md)
- [BGE-M3 论文](https://arxiv.org/abs/2309.07597)
- [RRF 原始论文](https://dl.acm.org/doi/10.1145/1571941.1572114)
