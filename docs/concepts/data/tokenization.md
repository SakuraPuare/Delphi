# 分词与 Token

Token 是 LLM 处理文本的基本单位。理解分词机制，对于优化 RAG 的分块策略、估算成本、避免上下文溢出至关重要。

## 什么是 Token

Token 不等于单词，也不等于字符。它是介于两者之间的文本片段，由分词器（Tokenizer）决定。

```
原始文本: "Delphi uses RAG"
分词结果: ["Del", "phi", " uses", " R", "AG"]  ← 5 个 token

原始文本: "你好世界"
分词结果: ["你好", "世界"]  ← 2 个 token（或 ["你", "好", "世", "界"] ← 4 个）
```

不同模型使用不同的分词器，同一段文本的 token 数量可能差异显著。

## 为什么 LLM 需要分词

神经网络只能处理数字，不能直接处理文本。分词是将文本转换为整数序列的过程：

```
文本 → 分词器 → Token ID 序列 → 词嵌入矩阵 → 向量序列 → Transformer
```

分词器维护一个**词表（Vocabulary）**，将每个 token 映射到唯一的整数 ID。现代 LLM 的词表大小通常在 32,000 ~ 150,000 之间。

词表越大，单个 token 能表示的信息越多（压缩率越高），但词嵌入矩阵也越大。

## BPE 算法

**字节对编码（Byte Pair Encoding，BPE）** 是目前最主流的分词算法，被 GPT、Llama、Qwen 等模型广泛采用。

### 训练过程

1. 从字符级词表开始（所有 Unicode 字节）
2. 统计相邻 token 对的出现频率
3. 将最高频的 token 对合并为新 token
4. 重复步骤 2-3，直到词表达到目标大小

```
初始: ["h", "e", "l", "l", "o", " ", "w", "o", "r", "l", "d"]

第1轮: "l"+"l" 频率最高 → 合并为 "ll"
结果: ["h", "e", "ll", "o", " ", "w", "o", "r", "l", "d"]

第2轮: "o"+" " 频率最高 → 合并为 "o "
...

最终: ["hello", " world"]  ← 高频词被合并为单个 token
```

### 为什么 BPE 有效

- **高频词**（如 `the`、`function`、`import`）成为单个 token，节省序列长度
- **罕见词**被拆分为子词，保证任意文本都能编码（无 OOV 问题）
- **字节级 BPE**（如 GPT-2 使用）能处理任意 Unicode 字符

## Token vs 词 vs 字符

以英文为例，经验规则：**1 token ≈ 0.75 个单词 ≈ 4 个字符**

```
"Hello, world!"
字符数: 13
单词数: 2
Token数: 4  ["Hello", ",", " world", "!"]
```

中文的情况不同，汉字通常 1~2 个字符对应 1 个 token：

```
"你好，世界！"
字符数: 6
Token数: 6（每个汉字约 1 token，标点各 1 token）
```

代码的 token 密度更高，因为标识符、关键字通常被整体编码：

```python
def calculate_sum(a, b):
    return a + b
```

```
Token: ["def", " calculate", "_sum", "(", "a", ",", " b", "):", "\n", "    ", "return", " a", " +", " b"]
共约 14 个 token
```

## Token 计数与上下文窗口限制

每个模型都有最大上下文长度（以 token 计）。超出限制的内容会被截断或导致错误。

### 快速估算

| 内容类型 | 估算规则 |
|---------|---------|
| 英文散文 | 100 词 ≈ 75 token |
| 中文文本 | 100 字 ≈ 100 token |
| 源代码 | 100 字符 ≈ 30~50 token |
| Markdown | 介于散文和代码之间 |

### 精确计数

使用 `tiktoken`（OpenAI）或 `transformers`（HuggingFace）进行精确计数：

```python
# 使用 transformers 计算 Qwen 的 token 数
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-Coder-7B-Instruct")

text = "def hello_world():\n    print('Hello, Delphi!')"
tokens = tokenizer.encode(text)
print(f"Token 数量: {len(tokens)}")  # 输出: Token 数量: 16
```

## 不同模型的分词差异

同一段代码，不同模型的 token 数量可能相差 20%~40%：

```python
code = "import numpy as np\nresult = np.array([1, 2, 3]).sum()"
```

| 模型 | 词表大小 | Token 数（示例） |
|------|---------|----------------|
| GPT-4o (cl100k) | 100,277 | ~18 |
| Llama 3 | 128,256 | ~17 |
| Qwen2.5 | 151,936 | ~16 |
| DeepSeek-V3 | 102,400 | ~18 |

Qwen 系列词表更大，对中文和代码的压缩率更高，相同内容消耗的 token 更少。

## 对 RAG 的影响

### 分块大小（Chunk Size）

RAG 将文档切分为块（chunk）再存入向量数据库。分块大小应以 **token** 为单位，而非字符数：

```python
# 错误做法：按字符数分块
chunk_size = 500  # 字符

# 正确做法：按 token 数分块
chunk_size = 512  # token（约 400 个英文单词，或 512 个汉字）
```

分块大小的权衡：

| 分块大小 | 优点 | 缺点 |
|---------|------|------|
| 小（128~256 token） | 检索精度高，噪声少 | 可能截断完整语义 |
| 中（512~1024 token） | 平衡精度与完整性 | 推荐默认值 |
| 大（2048+ token） | 保留更多上下文 | 检索噪声增加，速度慢 |

### 成本估算

使用闭源 API 时，费用按 token 计算。了解 token 数量有助于预算控制：

```
文档库大小: 10 MB 纯文本
≈ 10,000,000 字符
≈ 2,500,000 token（英文）

嵌入成本（text-embedding-3-small）:
2,500,000 token × $0.02/1M token = $0.05（一次性索引）

每次查询（假设检索 5 个 chunk，每 chunk 512 token）:
输入: 512×5 + 200（问题）= 2760 token
输出: ~500 token
成本: 约 $0.003/次
```

Delphi 本地部署无 API 费用，但了解 token 数量仍有助于优化推理速度。

## Delphi 如何处理 Token 限制

Delphi 在多个环节管理 token 预算：

### 1. 索引阶段

```yaml
# config.yaml
indexing:
  chunk_size: 512        # 每块最大 token 数
  chunk_overlap: 64      # 相邻块重叠 token 数（保持语义连续性）
  tokenizer: qwen2.5     # 使用与 LLM 一致的分词器计数
```

### 2. 检索阶段

检索到的 chunk 在送入 LLM 前，会计算总 token 数，确保不超过上下文窗口：

```
上下文窗口: 32,768 token
系统提示:   ~500 token
用户问题:   ~100 token
可用于检索结果: 32,768 - 500 - 100 - 500（回答预留）= 31,668 token
最多可放入: 31,668 / 512 ≈ 61 个 chunk
```

### 3. 动态截断

当检索结果超出预算时，Delphi 按相关性分数从高到低保留，丢弃低分 chunk，而非简单截断文本中间。

## 延伸阅读

- [上下文窗口](./context-window.md)
- [混合检索](./hybrid-search.md)
- [大语言模型基础](./llm.md)
- [BPE 原始论文](https://arxiv.org/abs/1508.07909)
