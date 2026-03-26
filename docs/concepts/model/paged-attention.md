# PagedAttention 与推理优化

PagedAttention 是 vLLM 项目提出的核心技术，通过借鉴操作系统虚拟内存的思想，将 LLM 推理吞吐量提升 2-4 倍。

## KV Cache：LLM 推理的内存瓶颈

### 什么是 KV Cache？

Transformer 的注意力机制在生成每个 token 时，需要访问所有之前 token 的 Key 和 Value 向量。为避免重复计算，这些向量会被缓存下来，即 KV Cache：

```
生成过程示意（生成第 4 个 token）：

输入序列：[你] [好] [世] → 生成 [界]

KV Cache 内容：
  K_1, V_1  ← "你" 的 Key/Value
  K_2, V_2  ← "好" 的 Key/Value
  K_3, V_3  ← "世" 的 Key/Value

注意力计算：Q_4 × [K_1, K_2, K_3] → 权重 → 加权 [V_1, V_2, V_3]
```

没有 KV Cache，生成 1000 个 token 的序列需要计算 1000 次完整的注意力，复杂度 O(n²)。有了 KV Cache，每步只需 O(n) 计算。

### KV Cache 的内存开销

KV Cache 的大小与序列长度成正比，对于大模型来说相当可观：

```
KV Cache 大小计算（以 Llama-2-7B 为例）：

层数：32
注意力头数：32
头维度：128
精度：FP16（2 字节）

每 token 的 KV Cache：
  = 2（K+V）× 32（层）× 32（头）× 128（维度）× 2（字节）
  = 524,288 字节 ≈ 0.5 MB / token

2048 token 序列：~1 GB
4096 token 序列：~2 GB
```

## 传统推理的内存浪费

### 静态内存分配

传统推理框架（如早期的 HuggingFace Transformers）在请求开始时就为 KV Cache 预分配最大长度的内存：

```
传统方式（max_length = 2048）：

请求 A（实际生成 200 tokens）：
  ┌──────────────────────────────────────────┐
  │ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
  │ 已用 200    浪费 1848 tokens 的空间       │
  └──────────────────────────────────────────┘

请求 B（实际生成 1500 tokens）：
  ┌──────────────────────────────────────────┐
  │ ████████████████████████████████████░░░░ │
  │ 已用 1500              浪费 548           │
  └──────────────────────────────────────────┘
```

这导致两个严重问题：
1. **内存碎片**：大量已分配但未使用的空间
2. **并发受限**：显存被少数请求占满，其他请求只能排队

### 批处理的困境

传统批处理要求同一批次的所有序列长度相同（或 padding 到相同长度），进一步浪费计算和内存。

## PagedAttention：虚拟内存思想的迁移

### 核心思想

PagedAttention 将 KV Cache 组织为固定大小的"页"（block），类似操作系统的内存分页：

```
PagedAttention 内存布局：

物理显存（分为固定大小的 block，每 block = 16 tokens）：

Block 0  │ K0,V0 │ K1,V1 │ ... │ K15,V15 │
Block 1  │ K0,V0 │ K1,V1 │ ... │ K15,V15 │
Block 2  │ K0,V0 │ K1,V1 │ ... │ K15,V15 │
...

逻辑序列到物理 block 的映射表（Block Table）：

请求 A（200 tokens）：逻辑块 [0,1,...,12] → 物理块 [3,7,1,...,9]
请求 B（1500 tokens）：逻辑块 [0,1,...,93] → 物理块 [0,2,4,...,15]
```

### 按需分配

KV Cache 只在实际需要时才分配新的 block，不再预留最大长度：

```
请求生成过程：

生成 token 1-16：分配 Block 5
生成 token 17-32：分配 Block 12
生成 token 33-48：分配 Block 2
...

序列结束后：立即释放所有 block，供其他请求使用
```

### 内存利用率对比

```
传统方式 vs PagedAttention（8× A100，处理混合长度请求）：

传统方式：
  显存利用率 ~20-40%（大量碎片和预留空间）
  并发请求数：~10-20

PagedAttention：
  显存利用率 ~90%+
  并发请求数：~100-200（提升 5-10×）
```

## Continuous Batching（连续批处理）

### 传统批处理的问题

传统推理以"批次"为单位处理请求：一批请求全部完成后，才开始处理下一批。

```
传统批处理时间线：

批次 1：[请求A(长)] [请求B(短)] [请求C(中)]
         ████████████████████████████████████  A 完成
         ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░  B 完成，等待 A
         ████████████████░░░░░░░░░░░░░░░░░░░  C 完成，等待 A
                                              ↑ GPU 空闲
批次 2：[请求D] [请求E] [请求F]
         ████...
```

短请求完成后，GPU 在等待长请求时处于半空闲状态。

### Continuous Batching 的解决方案

一旦某个请求完成，立即将新请求插入批次，GPU 始终保持满负荷：

```
Continuous Batching 时间线：

时刻 0：批次 = [A, B, C]
时刻 t1：B 完成 → 批次 = [A, C, D]（D 立即加入）
时刻 t2：C 完成 → 批次 = [A, D, E]（E 立即加入）
时刻 t3：A 完成 → 批次 = [D, E, F]（F 立即加入）

GPU 利用率：接近 100%
```

这也称为 **Inflight Batching** 或 **Iteration-level Scheduling**。

## 投机解码（Speculative Decoding）

简要介绍另一项推理优化技术：

```
基本思路：

小模型（draft model）快速生成 k 个候选 token
大模型（target model）并行验证这 k 个 token
  ├─ 全部接受：节省了 k-1 次大模型前向传播
  └─ 部分接受：从第一个拒绝处重新生成

适用场景：输出高度可预测时（如代码补全、翻译）
典型加速：1.5-3×
```

vLLM 支持投机解码，可通过配置启用。

## 吞吐量提升的量化数据

vLLM 论文中的基准测试数据（A100 80G，LLaMA-13B）：

```
吞吐量对比（tokens/second，ShareGPT 数据集）：

HuggingFace TGI（传统）：  ████████░░░░░░░░░░░░  ~1,000 tokens/s
vLLM（PagedAttention）：   ████████████████████  ~2,200 tokens/s

提升：约 2.2×

在高并发场景（100+ 并发请求）下提升更显著，可达 3-4×
```

实际提升幅度取决于：
- 请求长度分布（越不均匀，提升越大）
- 并发请求数（越高，提升越大）
- 模型大小和硬件配置

## vLLM 在 Delphi 中的实现

Delphi 使用 vLLM 作为 GPU 推理后端，自动获得上述所有优化：

### 启动配置

```yaml
# Delphi vLLM 后端配置
inference:
  backend: vllm
  model: Qwen/Qwen2.5-7B-Instruct-AWQ
  
  # PagedAttention 相关
  gpu_memory_utilization: 0.90  # 使用 90% 显存作为 KV Cache
  max_num_seqs: 256             # 最大并发序列数
  max_model_len: 8192           # 最大序列长度
  
  # 可选：投机解码
  speculative_model: Qwen/Qwen2.5-0.5B-Instruct
  num_speculative_tokens: 5
```

### RAG 场景的特殊考量

Delphi 的 RAG 流程会将检索到的文档片段拼接到 prompt 中，这意味着：

1. **输入长度较长**：通常 1000-4000 tokens 的上下文
2. **输出长度较短**：回答通常 100-500 tokens
3. **Prefix Caching 收益大**：相同知识库的查询往往共享 system prompt

vLLM 的 Prefix Caching 功能可以缓存重复的 prompt 前缀（如 system prompt），进一步减少计算：

```yaml
inference:
  enable_prefix_caching: true  # 缓存重复的 prompt 前缀
```

在 Delphi 的典型工作负载下，Prefix Caching 可将首 token 延迟降低 30-50%。

## 延伸阅读

- [vLLM 论文：Efficient Memory Management for Large Language Model Serving with PagedAttention](https://arxiv.org/abs/2309.06180)
- [Continuous Batching 详解](https://www.anyscale.com/blog/continuous-batching-llm-inference)
- [vLLM 官方文档](https://docs.vllm.ai/)
- [投机解码论文](https://arxiv.org/abs/2211.17192)
