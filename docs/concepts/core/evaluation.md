# RAG 评估指标

构建 RAG 系统容易，但判断它是否真的"好用"却很难。评估体系是 RAG 工程化的关键环节——没有量化指标，优化就是盲目的。

## 为什么 RAG 评估很重要

RAG 系统有两个可能出错的环节：**检索**和**生成**。

```
用户问题 → [检索] → 相关文档块 → [生成] → 最终回答
              ↑                        ↑
         可能检索错误              可能生成幻觉
```

两个环节的错误性质不同，需要不同的指标来衡量。只看最终回答质量，无法定位问题出在哪里。

## 检索指标

### Recall@K（召回率@K）

在返回的前 K 个结果中，有多少相关文档被找到：

```
Recall@K = 找到的相关文档数 / 总相关文档数

示例：
  总相关文档：5 篇
  Top-5 中找到：4 篇
  Recall@5 = 4/5 = 0.8
```

衡量检索的**覆盖能力**，Recall@K 越高，遗漏的相关信息越少。

### Precision@K（精确率@K）

在返回的前 K 个结果中，有多少是真正相关的：

```
Precision@K = 相关文档数 / K

示例：
  Top-5 中有 3 篇相关
  Precision@5 = 3/5 = 0.6
```

衡量检索的**准确性**，Precision@K 越高，噪声越少，LLM 不会被无关内容干扰。

### MRR（Mean Reciprocal Rank，平均倒数排名）

衡量第一个相关结果出现的位置：

```
RR = 1 / (第一个相关结果的排名)

示例：
  第一个相关结果排在第 2 位 → RR = 1/2 = 0.5
  第一个相关结果排在第 1 位 → RR = 1/1 = 1.0

MRR = 所有查询的 RR 平均值
```

对于 RAG 来说，最相关的文档排在越前面越好，MRR 直接反映这一点。

### NDCG（Normalized Discounted Cumulative Gain）

考虑相关性程度和排名位置的综合指标：

```
DCG@K = Σ (relevance_i / log2(i+1))  for i=1..K

NDCG@K = DCG@K / IDCG@K  （IDCG 是理想排序的 DCG）
```

NDCG 支持多级相关性（如：非常相关=3，相关=2，略相关=1），比 Precision/Recall 更细腻。

## 生成指标

这三个指标由 RAGAS 框架提出，是目前最广泛使用的 RAG 生成质量评估标准。

### Faithfulness（忠实度）

回答中的每个陈述是否都能从检索到的文档中找到依据：

```
Faithfulness = 有文档支撑的陈述数 / 回答中的总陈述数

高 Faithfulness → 回答没有"编造"内容
低 Faithfulness → 回答包含幻觉（hallucination）
```

这是 RAG 最核心的指标之一。RAG 的目的就是用检索到的事实约束 LLM，Faithfulness 直接衡量这个约束是否有效。

### Answer Relevancy（回答相关性）

回答是否真正回应了用户的问题：

```
高 Answer Relevancy → 回答切题，没有跑题或废话
低 Answer Relevancy → 回答虽然忠实于文档，但没有回答用户的问题
```

通常通过让 LLM 根据回答反向生成问题，再计算与原问题的相似度来评估。

### Context Relevancy（上下文相关性）

检索到的文档块与用户问题的相关程度：

```
高 Context Relevancy → 检索精准，文档块都与问题相关
低 Context Relevancy → 检索到大量无关内容，信噪比低
```

Context Relevancy 低会导致 LLM 被无关信息干扰，即使 Faithfulness 高，回答质量也会下降。

## 端到端指标

### Answer Correctness（回答正确性）

将最终回答与标准答案（ground truth）对比，综合衡量事实准确性：

```
Answer Correctness = α × Factual Similarity + (1-α) × Semantic Similarity
```

需要人工标注的标准答案，成本较高，但是最直接反映用户体验的指标。

## 评估框架

### RAGAS

最流行的 RAG 评估框架，提出了 Faithfulness、Answer Relevancy、Context Relevancy 等核心指标，支持无参考答案的评估（用 LLM 作为评判者）。

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_relevancy

result = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy, context_relevancy]
)
```

### TruLens

Trulera 开发的评估框架，支持 RAG 三元组评估（Context Relevance、Groundedness、Answer Relevance），提供可视化 Dashboard。

### DeepEval

支持更多指标类型，包括幻觉检测、毒性检测等，可集成到 CI/CD 流程中作为自动化测试。

## 如何构建评估数据集

评估数据集是评估体系的基础，通常包含：

```
{
  "question": "Delphi 支持哪些文件格式？",
  "ground_truth": "Delphi 支持 PDF、Markdown、代码文件等格式",
  "contexts": ["从知识库检索到的相关文档块..."],
  "answer": "系统生成的回答..."
}
```

构建方式：

1. **人工标注**：质量最高，成本最高，适合核心测试集
2. **LLM 生成**：用 LLM 从文档中自动生成问答对，再人工审核
3. **用户日志**：收集真实用户问题，人工标注答案

建议至少准备 50-100 个高质量问答对作为基准测试集。

## Delphi 的评估计划

Delphi 计划在以下维度评估 RAG 质量：

**检索层**：针对代码搜索场景，重点评估 Recall@5 和 MRR，确保相关代码片段能被找到。

**生成层**：使用 RAGAS 框架评估 Faithfulness，防止 LLM 在代码问答中编造不存在的 API 或参数。

**端到端**：构建包含代码理解、文档问答两类问题的评估集，定期运行回归测试，防止系统更新引入质量退化。

## 延伸阅读

- [检索增强生成 (RAG)](./rag.md) — RAG 系统整体架构
- [重排序模型 (Reranker)](./reranker.md) — 提升检索排序质量
- [混合检索](./hybrid-search.md) — 提升检索召回率的方案
