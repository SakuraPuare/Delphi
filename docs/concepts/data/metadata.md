# 元数据与知识图谱

在 RAG 系统中，元数据是附加在每个文档块上的结构化描述信息。它不参与语义检索，但能大幅提升检索的精准度和上下文质量。

## 什么是元数据？

向量数据库中存储的每个文档块，除了文本内容和向量之外，还可以携带一组键值对形式的元数据：

```
文档块 = {
  "content": "def forward(self, x): ...",   // 文本内容
  "vector": [0.12, -0.34, ...],             // 嵌入向量
  "metadata": {                              // 元数据
    "file_path": "models/transformer.py",
    "language": "python",
    "function_name": "forward",
    "line_start": 42
  }
}
```

元数据的作用是在向量相似度之外，提供额外的过滤和排序维度。

## 元数据的三种类型

### 结构性元数据

描述文档的物理结构和来源：

- **文件路径**：`src/api/routes.py`
- **文件类型**：`python`、`markdown`、`pdf`
- **行号范围**：`line_start: 42, line_end: 67`
- **文件大小**、**创建时间**、**修改时间**
- **文档标题**、**章节层级**

### 语义性元数据

描述内容的语义属性：

- **语言**：编程语言或自然语言
- **内容类型**：函数定义、类定义、注释、文档段落
- **摘要**：由 LLM 生成的内容摘要
- **关键词**：提取的重要术语

### 关系性元数据

描述文档块与其他内容的关系：

- **父文档 ID**：该块属于哪个文件
- **相邻块 ID**：前一块和后一块
- **引用关系**：该函数调用了哪些其他函数
- **依赖关系**：该模块依赖哪些包

## 元数据如何改善检索

### 过滤（Filtering）

在向量检索之前或之后，用元数据过滤掉不相关的结果：

```python
# 只在 Python 文件中搜索
results = collection.query(
    query_vector=query_embedding,
    query_filter=Filter(
        must=[FieldCondition(key="language", match=MatchValue(value="python"))]
    ),
    limit=10
)
```

这比纯向量检索更精准，避免跨语言的误匹配。

### 权重提升（Boosting）

根据元数据调整检索结果的排名：

```
同一文件内的结果  → 分数 × 1.5（局部性优先）
最近修改的文件    → 分数 × 1.2（时效性优先）
核心模块的文件    → 分数 × 1.3（重要性优先）
```

### 上下文扩展（Context Enrichment）

检索到某个块后，利用关系元数据获取更多上下文：

```
检索到函数 forward() 的实现
  → 通过元数据找到其所在的类 TransformerBlock
  → 附加类的文档字符串作为额外上下文
  → 通过依赖关系找到它调用的 attention() 函数签名
```

## 代码专属元数据

代码文件的元数据比普通文档更丰富，Tree-sitter 等工具可以自动提取：

```python
{
  "file_path": "src/models/attention.py",
  "language": "python",
  "namespace": "src.models.attention",        // 模块路径
  "symbol_type": "function",                  // function/class/method
  "symbol_name": "scaled_dot_product",
  "signature": "def scaled_dot_product(q, k, v, mask=None) -> Tensor",
  "docstring": "计算缩放点积注意力...",
  "dependencies": ["torch", "torch.nn.functional"],  // import 的依赖
  "called_by": ["MultiHeadAttention.forward"],       // 被哪些函数调用
  "calls": ["torch.matmul", "F.softmax"],            // 调用了哪些函数
  "line_start": 15,
  "line_end": 34
}
```

这些元数据让代码搜索可以按语言、符号类型、命名空间精确过滤，大幅减少噪声。

## 文档专属元数据

```python
{
  "source": "docs/architecture.md",
  "title": "系统架构设计",
  "heading_path": "系统架构设计 > 检索层 > 向量数据库",  // 章节路径
  "author": "team",
  "last_modified": "2024-01-15",
  "doc_type": "markdown",
  "chunk_index": 3,          // 该块在文档中的位置
  "total_chunks": 12         // 文档总块数
}
```

`heading_path` 特别有用——它告诉 LLM 这段内容在文档结构中的位置，帮助生成更准确的引用。

## 从元数据到知识图谱

当关系性元数据积累到一定程度，就自然形成了一个**知识图谱**：

```
文件 A ──imports──> 模块 B
函数 foo ──calls──> 函数 bar
类 Model ──inherits──> 类 BaseModel
文档 X ──references──> 文档 Y
```

知识图谱可以支持更复杂的检索模式：

- **图遍历**：找到所有调用了某个函数的代码路径
- **影响分析**：修改某个函数会影响哪些下游调用者
- **语义聚类**：将功能相关的代码块组织在一起

这是 RAG 系统从"文档检索"进化到"知识理解"的关键方向，也是 GraphRAG 等新兴技术的基础。

## Delphi 如何使用元数据

Delphi 在索引阶段为每个文档块提取并存储元数据，存入 Qdrant 的 payload 字段：

**代码文件**：通过 Tree-sitter 提取语言、符号类型、函数签名、行号等结构化信息。

**文档文件**：提取文件路径、标题、章节层级、修改时间等信息。

**检索时**：支持按文件类型、编程语言、符号类型过滤，将元数据拼接到 Prompt 中，帮助 LLM 了解代码片段的来源和上下文。

知识图谱功能（依赖关系分析、跨文件引用追踪）是 Delphi 的未来规划方向。

## 延伸阅读

- [代码分块策略](./chunking.md) — 元数据在分块阶段的提取
- [Tree-sitter 语法解析](./tree-sitter.md) — 代码元数据的提取工具
- [向量数据库](../core/vector-database.md) — 元数据的存储与过滤查询
