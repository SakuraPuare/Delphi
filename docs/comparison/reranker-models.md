# Reranker 模型对比

本文对比主流 Reranker 模型在 Delphi 场景下的适用性，重点关注离线部署能力、代码理解效果与推理延迟。

## 模型概览对比

| 模型 | 精度 | 延迟 | 模型大小 | 多语言 | 代码理解 | 开源/闭源 | CPU 可用 |
|------|------|------|---------|-------|---------|----------|---------|
| BGE-Reranker-v2-M3 | 高 | 低 | 568M | 支持 | 良好 | 开源 | 可用 |
| Cohere Rerank v3 | 极高 | 中（网络延迟）| N/A | 100+ 语言 | 良好 | 闭源 | 不可用 |
| Jina Reranker v2 | 高 | 低 | 278M | 多语言 | 一般 | 开源 | 可用 |
| cross-encoder/ms-marco | 中 | 低 | 22M–340M | 英文为主 | 差 | 开源 | 可用 |
| RankLLM | 极高 | 高 | 7B+ | 多语言 | 良好 | 开源 | 不推荐 |
| ColBERT reranking | 高 | 极低 | 110M–568M | 多语言 | 良好 | 开源 | 可用 |

## Reranking 架构对比

### Cross-Encoder（交叉编码器）

将查询和文档拼接后一起输入模型，输出相关性分数。

- 优点：精度高，充分利用查询-文档交互信息
- 缺点：每对（查询, 文档）都需要独立推理，延迟随候选数量线性增长
- 代表模型：BGE-Reranker-v2-M3、Jina Reranker v2、cross-encoder/ms-marco

适合候选集较小（Top-50 以内）的精排场景，是 RAG 系统中最常用的 reranking 方式。

### Late Interaction（延迟交互）

以 ColBERT 为代表，查询和文档分别编码为 token 级向量，检索时通过 MaxSim 操作计算相关性。

- 优点：文档向量可预计算缓存，检索延迟极低
- 缺点：存储开销大（每文档存储多个向量），索引构建复杂
- 代表模型：ColBERT v2、BGE-M3 的 ColBERT 输出头

适合需要极低延迟的场景，或作为 BGE-M3 混合检索的一部分使用。

### LLM-based Reranking

使用大语言模型（如 GPT-4、LLaMA）直接判断文档与查询的相关性，通常通过 listwise 或 pointwise 提示实现。

- 优点：理解能力最强，可处理复杂语义关系
- 缺点：延迟极高（秒级），成本高，不适合实时检索
- 代表方案：RankLLM、RankGPT

在 Delphi 的本地实时检索场景中，LLM-based reranking 的延迟不可接受。

## 各模型详细分析

**BGE-Reranker-v2-M3**
BAAI 发布的多语言 Cross-Encoder，基于 BGE-M3 的编码器架构微调。支持 100+ 语言，在多语言重排序基准上表现领先。模型大小约 568M，CPU 推理延迟在可接受范围内（Top-20 候选约 200ms）。与 BGE-M3 Embedding 同源，两者配合使用效果最佳。

**Cohere Rerank v3**
精度极高，支持多语言和代码，但仅提供 API 访问，无法离线部署，直接排除。

**Jina Reranker v2**
开源 Cross-Encoder，模型较小（278M），CPU 友好，但多语言能力和代码理解弱于 BGE-Reranker-v2-M3。

**cross-encoder/ms-marco**
HuggingFace 上的经典 Cross-Encoder 系列，主要针对英文问答场景训练，对中文和代码的支持有限。适合英文文档检索，不适合 Delphi 的多语言代码场景。

**RankLLM**
基于 7B+ 参数 LLM 的重排序框架，精度最高，但推理延迟在 CPU 上达到秒级甚至分钟级，不适合交互式检索。

**ColBERT reranking**
延迟极低，但需要预先构建 ColBERT 索引，存储开销约为 Dense 索引的 10 倍。在 Delphi 中，BGE-M3 的 ColBERT 输出可作为混合检索的补充，而非独立的 reranking 方案。

## 离线部署可用性

| 模型 | 离线可用 | 原因 |
|------|---------|------|
| BGE-Reranker-v2-M3 | 可用 | HuggingFace 开源，本地加载 |
| Cohere Rerank v3 | 不可用 | 仅 API |
| Jina Reranker v2 | 可用 | 开源权重 |
| cross-encoder/ms-marco | 可用 | 开源权重 |
| RankLLM | 可用（受限）| 需要大显存 GPU |
| ColBERT reranking | 可用 | 开源，但索引开销大 |

## 为什么 Delphi 选择 BGE-Reranker-v2-M3

1. **与 Embedding 模型同源**：BGE-M3 + BGE-Reranker-v2-M3 是同一团队的配套方案，语义空间对齐，联合使用效果最优
2. **离线可用**：完整开源，无需网络连接，符合 Delphi 离线设计原则
3. **CPU 可运行**：568M 参数在现代 CPU 上推理延迟约 100–300ms（Top-20 候选），对用户体验影响可接受
4. **多语言支持**：覆盖中文、英文及代码混合场景，无需针对不同语言切换模型
5. **代码理解能力**：在代码相关的重排序任务上表现优于 ms-marco 系列
6. **社区支持**：BAAI 持续维护，HuggingFace 集成完善，文档详尽

在 Delphi 的典型检索流程中，BGE-M3 负责初步召回（Top-50），BGE-Reranker-v2-M3 对候选结果精排（Top-50 → Top-5），两者形成完整的两阶段检索管线。
