# 文本切分策略 (Chunking)

在 RAG 系统中，文档在被向量化之前必须先被切分成若干小块（chunk）。切分策略直接决定了检索质量的上限——切分得好，检索到的内容精准且完整；切分得差，再好的向量模型和重排序器也无法弥补。

## 为什么切分如此重要

向量嵌入模型有输入长度限制（通常为 512 或 8192 个 token）。即使没有长度限制，将整篇文档作为一个向量也会导致严重的语义稀释：一个包含 50 个话题的文档，其向量是所有话题的"平均"，对任何单一查询的相关性都会很低。

切分面临一个根本性的权衡：

```
chunk 太大                    chunk 太小
─────────────────────────────────────────
✗ 语义稀释，相关性下降         ✗ 上下文丢失，答案不完整
✗ 超出模型 token 限制          ✗ 需要更多 chunk 才能覆盖答案
✗ 噪声多，LLM 难以聚焦         ✗ 跨 chunk 的逻辑关系断裂
✓ 保留完整上下文               ✓ 检索精度高
```

没有放之四海而皆准的最优 chunk 大小，需要根据内容类型、查询模式和模型能力综合决定。

## 朴素切分策略

### 固定大小切分（Fixed-size Chunking）

最简单的策略：每隔 N 个字符（或 token）切一刀。

```
原文：The quick brown fox jumps over the lazy dog. It was a sunny day.

chunk_size=30, overlap=0:
  chunk 1: "The quick brown fox jumps ove"
  chunk 2: "r the lazy dog. It was a sunn"
  chunk 3: "y day."
```

问题显而易见：切割点完全不考虑语义，单词和句子会被截断。这种方式只适合对内容结构没有任何假设的场景（如二进制数据的文本表示）。

### 句子切分（Sentence-based Chunking）

以句子为单位切分，每个 chunk 包含若干完整句子。

```python
# 伪代码
sentences = split_by_sentence(text)  # 按 "。！？.!?" 分割
chunks = group_sentences(sentences, max_tokens=200)
```

优点是每个 chunk 都是语义完整的句子，不会截断单词。缺点是句子之间的上下文关系可能丢失，且对于技术文档中的长句效果不佳。

### 段落切分（Paragraph-based Chunking）

以段落（空行分隔）为单位切分。对于结构良好的文档（如 Markdown、技术博客），这是一个合理的基线方案。

## 进阶切分策略

### 递归字符切分（Recursive Character Splitting）

LangChain 推广的策略。按优先级尝试不同的分隔符，直到 chunk 足够小：

```
分隔符优先级（以 Markdown 为例）：
  1. "\n\n"   （段落）
  2. "\n"     （换行）
  3. "。" "." （句子）
  4. "，" "," （子句）
  5. " "      （单词）
  6. ""       （字符）
```

算法流程：

```
输入文本
  │
  ▼
用最高优先级分隔符分割
  │
  ├─ 所有块都 ≤ max_size？→ 完成
  │
  └─ 有块 > max_size？
       │
       ▼
     对超大块用下一级分隔符递归处理
```

这种方式在保持语义完整性的同时，能处理各种长度的文本，是通用文档的推荐基线。

### 语义切分（Semantic Chunking）

不依赖固定分隔符，而是通过计算相邻句子的语义相似度来决定切割点：

```
句子 1: "Python 是一种解释型语言。"          ─┐
句子 2: "它支持动态类型系统。"                 │ 相似度高 → 同一 chunk
句子 3: "Python 广泛用于数据科学领域。"       ─┘

句子 4: "数据库是持久化存储数据的系统。"      ─┐ 相似度低 → 切割点
句子 5: "关系型数据库使用 SQL 查询语言。"     ─┘ 新 chunk 开始
```

实现方式：将每个句子嵌入为向量，计算相邻句子的余弦相似度，当相似度骤降时插入切割点。

优点是切割点在语义边界处，chunk 内部主题一致。缺点是需要额外的嵌入计算，处理速度较慢。

### AST 切分（AST-based Chunking）

专为代码设计的策略，使用语法树（如 Tree-sitter）按语言结构切分：

```
代码文件
  │
  ▼
Tree-sitter 解析 → 语法树
  │
  ▼
提取顶层节点：
  ├── class MyClass (行 1-50)     → chunk A
  │     ├── method __init__       → chunk A1（若类太大则细分）
  │     └── method process        → chunk A2
  ├── function helper (行 52-70)  → chunk B
  └── function main (行 72-90)    → chunk C
```

每个 chunk 都是语义完整的代码单元（函数、类、方法），不会在逻辑中间截断。详见 [Tree-sitter 与 AST 解析](./tree-sitter.md)。

## Chunk 大小与 Token 限制

Token 是 LLM 处理文本的基本单位，大致对应：
- 英文：1 token ≈ 4 个字符 ≈ 0.75 个单词
- 中文：1 token ≈ 1-2 个汉字

常见的 chunk size 参考值：

| 场景 | 推荐 chunk size | 说明 |
|------|----------------|------|
| 问答型查询 | 256–512 tokens | 精准匹配，减少噪声 |
| 摘要型查询 | 512–1024 tokens | 需要更多上下文 |
| 代码函数 | 按函数体实际大小 | 不强制截断 |
| 长文档段落 | 512–768 tokens | 平衡精度与完整性 |

注意：chunk size 指的是输入给嵌入模型的大小，而不是最终传给 LLM 的大小。检索到的多个 chunk 会拼接后传给 LLM，需要确保总长度在 LLM 的上下文窗口内。

## 重叠策略（Overlap）

固定大小切分和递归切分通常配合重叠使用，避免关键信息恰好落在切割点处：

```
chunk_size=100 tokens, overlap=20 tokens:

chunk 1: [token 1  .............. token 100]
chunk 2:              [token 81 .............. token 180]
chunk 3:                           [token 161 ........... token 260]
                      ↑ 重叠区域 ↑
```

重叠的代价是存储和计算量增加（约 overlap/chunk_size 的比例）。对于语义切分和 AST 切分，通常不需要重叠，因为切割点本身就在语义边界处。

## 元数据富化（Metadata Enrichment）

单纯的文本 chunk 在检索后缺乏上下文。为每个 chunk 附加元数据，可以显著提升检索结果的可用性：

```json
{
  "content": "def calculate(x, y):\n    return x + y",
  "metadata": {
    "source_file": "src/math_utils.py",
    "chunk_type": "function",
    "symbol_name": "calculate",
    "start_line": 42,
    "end_line": 45,
    "language": "python",
    "parent_class": null,
    "doc_title": "数学工具函数",
    "last_modified": "2025-03-01"
  }
}
```

元数据的用途：
- **过滤检索**：只在特定文件或特定语言中搜索
- **结果展示**：向用户展示来源文件和行号
- **上下文重建**：根据 `parent_class` 找到相关的类定义
- **时效性排序**：优先返回最近修改的内容

## Delphi 的切分策略

Delphi 针对不同内容类型采用不同的切分策略：

### 代码文件

```
策略：AST 切分（Tree-sitter）
粒度：函数 / 方法 / 类
回退：若函数体超过 1024 tokens，按内部块结构递归细分
元数据：文件路径、语言、符号名、行号、父类名
```

### 文档文件（Markdown / reStructuredText）

```
策略：标题感知的递归切分
粒度：按 H2/H3 标题划分章节，章节内递归切分
重叠：章节间无重叠，段落间 50 tokens 重叠
元数据：文档标题、章节标题、文件路径
```

### 媒体转录文本（音视频字幕）

```
策略：时间戳感知的句子切分
粒度：约 30 秒的语音对应的文本量（~150 tokens）
重叠：前后各保留 1-2 句（约 30 tokens）
元数据：媒体文件名、起止时间戳、说话人（若有）
```

### 切分流程总览

```
文件输入
  │
  ▼
检测文件类型
  ├── .py / .cpp / .ts / .go / ... → AST 切分器
  ├── .md / .rst / .txt            → 文档切分器
  └── .srt / .vtt / 转录 JSON      → 媒体切分器
  │
  ▼
生成 chunk 列表（content + metadata）
  │
  ▼
过滤空块、去重
  │
  ▼
批量向量化（Embedding）
  │
  ▼
写入向量数据库
```

这种分类处理的方式确保每种内容都以最适合其结构的方式被切分，最终提升端到端的检索质量。
