# Graph RAG 增强检索

## 概述

纯向量检索基于语义相似度匹配文本片段，在代码知识库场景下存在明显局限：

- **缺乏结构感知**：向量检索无法理解函数调用链、类继承等代码结构关系
- **上下文断裂**：检索到某个函数实现后，其调用者和被调用者往往不在结果中
- **跨文件盲区**：模块间的 import 依赖和接口关系难以通过语义相似度捕获

Graph RAG 通过代码符号关系图谱对向量检索结果进行扩展，将与检索命中代码存在调用、继承、包含等关系的关联代码片段自动补充到上下文中，让 LLM 获得更完整的代码理解视角。

## 工作原理

完整的检索流程分为三个阶段：

```
用户查询
   ↓
Query 改写（可选）
   ↓
BGE-M3 Embedding → Qdrant 向量检索 → Top-K 候选 Chunks
   ↓
Graph RAG 扩展：
   ├─ 在图谱中定位每个 chunk 包含的代码符号
   ├─ 通过关系边找到关联符号（调用者、被调用者、父类、子类等）
   ├─ 将关联符号转为 ScoredChunk，得分 = 原始 chunk 得分 × 衰减因子
   └─ 去重后合并到候选列表
   ↓
BGE-Reranker 精排 → Top-N 最终结果
   ↓
Prompt 组装 → vLLM 生成回答
```

Graph RAG 扩展发生在向量检索之后、Reranker 精排之前。扩展产生的 chunk 会和原始 chunk 一起参与 Reranker 排序，由 Reranker 决定最终是否保留。

## 架构图

```mermaid
flowchart TD
    Q[用户查询] --> RW[Query 改写]
    RW --> EMB[BGE-M3 Embedding]
    EMB --> VS[Qdrant 向量检索]
    VS --> CK[Top-K 候选 Chunks]

    CK --> GR{Graph RAG 开启?}
    GR -- 否 --> RR[BGE-Reranker 精排]
    GR -- 是 --> LOAD[加载项目图谱]

    LOAD --> MATCH[匹配 chunk 中的符号]
    MATCH --> EXPAND[遍历关系边收集关联符号]
    EXPAND --> DECAY[应用得分衰减]
    DECAY --> DEDUP[去重合并]
    DEDUP --> RR

    RR --> TOPN[Top-N 最终结果]
    TOPN --> PROMPT[Prompt 组装]
    PROMPT --> LLM[vLLM 生成回答]

    subgraph 图谱构建（离线）
        CODE[源代码文件] --> TS[Tree-sitter AST 解析]
        TS --> EXT[符号与关系提取]
        EXT --> GS[GraphStore 持久化]
    end

    GS -.-> LOAD
```

## 符号关系类型

图谱通过 Tree-sitter 对源代码进行 AST 解析，提取四种符号关系：

| 关系类型 | 含义 | 示例 |
|---------|------|------|
| `calls` | 函数/方法调用 | `retrieve()` 调用了 `expand_with_graph()` |
| `imports` | 模块导入依赖 | `rag.py` 导入了 `graph_rag` 模块 |
| `inherits` | 类继承关系 | `MyClient` 继承自 `BaseClient` |
| `contains` | 包含关系（类包含方法） | `GraphStore` 包含 `get()` 方法 |

### 符号数据模型

每个符号（`Symbol`）包含以下属性：

```python
@dataclass
class Symbol:
    name: str              # 符号名称，如 "retrieve"
    qualified_name: str    # 全限定名，格式 file_path::class::method
    kind: str              # "function" | "class" | "method" | "module"
    file_path: str         # 所在文件路径
    start_line: int        # 起始行号
    end_line: int          # 结束行号
    language: str          # 编程语言
```

关系（`Relation`）连接两个符号的 `qualified_name`：

```python
@dataclass
class Relation:
    source: str   # 源符号 qualified_name
    target: str   # 目标符号 qualified_name
    kind: str     # "calls" | "imports" | "inherits" | "contains"
```

## 扩展策略

### 双向遍历

`_collect_related_qnames()` 对图谱关系进行双向遍历：不仅查找当前符号调用了谁（出边），也查找谁调用了当前符号（入边）。这确保了调用者和被调用者都能被纳入上下文。

```python
def _collect_related_qnames(graph, symbol):
    qn = symbol.qualified_name
    related = set()
    for rel in graph.relations:
        if rel.source == qn:
            related.add(rel.target)   # 出边：当前符号调用/包含的目标
        elif rel.target == qn:
            related.add(rel.source)   # 入边：调用/包含当前符号的来源
    return related
```

### 得分衰减

图谱扩展的 chunk 得分按衰减因子（默认 `0.6`）计算：

```
扩展 chunk 得分 = 原始 chunk 得分 × _SCORE_DECAY (0.6)
```

同一个关联符号可能被多个原始 chunk 关联到，此时保留最高的衰减得分。衰减机制确保图谱扩展的结果在 Reranker 阶段不会无条件压过原始向量检索结果。

### 去重

扩展过程中通过 `(file_path, start_line, end_line)` 三元组进行去重：

1. 已在原始检索结果中的代码范围不会重复添加
2. 多条关系路径指向同一符号时只保留一份
3. 扩展结果按得分降序排列，默认取 top 5

## 配置说明

### use_graph_rag 开关

Graph RAG 默认启用。可通过 API 请求参数逐次控制：

```json
POST /query
{
    "question": "retrieve 函数的调用链是什么？",
    "project": "delphi",
    "top_k": 5,
    "use_graph_rag": true
}
```

将 `use_graph_rag` 设为 `false` 可关闭图谱扩展，退回纯向量检索 + Reranker 模式。

流式接口 `/query/stream` 同样支持该参数。

### 图谱存储

图谱以 JSON 文件持久化在 `~/.delphi/graphs/` 目录下，每个项目一个文件：

```
~/.delphi/graphs/
├── project-a.json
└── project-b.json
```

`GraphStore` 采用内存 + 文件双层缓存：优先从内存读取，未命中时从 JSON 文件加载。

### 支持的语言

符号提取基于 Tree-sitter，当前支持：

- Python（函数、类、方法、import）
- JavaScript / TypeScript（函数、类、箭头函数、import/require）

## 使用示例

### 场景：查询某个函数的实现细节

用户提问："`expand_with_graph` 函数是怎么工作的？"

1. 向量检索命中 `graph_rag.py` 中 `expand_with_graph` 函数的代码片段
2. Graph RAG 在图谱中找到该函数包含的符号，以及它调用的 `_find_symbols_in_chunk`、`_collect_related_qnames` 等内部函数
3. 同时找到调用了 `expand_with_graph` 的 `rag.py` 中的 `retrieve` 函数
4. 这些关联代码片段被加入候选列表，经 Reranker 排序后进入最终上下文
5. LLM 基于完整的调用链上下文生成更准确的回答

### 场景：理解类的继承体系

用户提问："`BaseClient` 有哪些子类？"

1. 向量检索命中 `BaseClient` 的定义
2. Graph RAG 通过 `inherits` 关系找到所有继承 `BaseClient` 的子类
3. 子类的代码片段被补充到上下文中
4. LLM 能够列出完整的继承体系并解释各子类的差异
