# 混合专家模型 (MoE)

混合专家模型（Mixture of Experts，MoE）是一种通过条件计算实现"大参数量、低计算量"的神经网络架构，是当前顶级开源模型（Mixtral、DeepSeek-V2）的核心技术。

## 什么是 MoE？

### 基本概念

MoE 的核心思想来自集成学习：与其用一个大网络处理所有问题，不如训练多个"专家"网络，每次只激活最适合当前输入的少数几个。

```
传统密集模型（Dense Model）：

输入 → [FFN 层（全部激活）] → 输出
         所有参数都参与计算
```

```
MoE 模型：

输入 → [Router] → 选择 Top-K 专家
         │
         ├─ Expert 1 ░░░░  （未选中，不计算）
         ├─ Expert 2 ████  （选中，参与计算）
         ├─ Expert 3 ░░░░  （未选中，不计算）
         ├─ Expert 4 ████  （选中，参与计算）
         ├─ Expert 5 ░░░░  （未选中，不计算）
         └─ Expert 6 ░░░░  （未选中，不计算）
         
输出 = 加权合并选中专家的输出
```

### 在 Transformer 中的位置

MoE 通常替换 Transformer 中的 FFN（前馈网络）层，注意力层保持不变：

```
标准 Transformer Block：
  输入 → LayerNorm → Multi-Head Attention → 残差
       → LayerNorm → FFN → 残差 → 输出

MoE Transformer Block：
  输入 → LayerNorm → Multi-Head Attention → 残差
       → LayerNorm → MoE Layer（Router + N×Expert FFN）→ 残差 → 输出
```

## Router（路由器）机制

Router 是 MoE 的核心组件，决定每个 token 由哪些专家处理。

### Top-K 路由

最常见的路由策略是 Top-K 软路由：

```python
# 简化的 Top-K 路由逻辑
def route(hidden_state, num_experts=8, top_k=2):
    # 计算每个专家的得分
    scores = linear(hidden_state)  # shape: [num_experts]
    scores = softmax(scores)
    
    # 选择得分最高的 K 个专家
    top_k_scores, top_k_indices = topk(scores, k=top_k)
    
    # 归一化权重
    weights = top_k_scores / sum(top_k_scores)
    
    return top_k_indices, weights
```

### 负载均衡

朴素的 Top-K 路由会导致"专家坍塌"——所有 token 都涌向少数几个专家，其他专家几乎不被使用。解决方案是在训练时加入辅助损失：

```
辅助损失 = λ × Σ(专家负载方差)

目标：让每个专家处理大致相同数量的 token
```

DeepSeek-V2 引入了更精细的"专家亲和力"机制，进一步改善负载均衡。

## 总参数量 vs 激活参数量

这是理解 MoE 效率的关键区别：

```
Mixtral 8×7B 为例：

总参数量：~47B（8 个专家，每个约 7B 等效）
激活参数量：~13B（每次只激活 2 个专家）

对比：
  Llama-2-13B（密集）：13B 总参数，13B 激活参数
  Mixtral 8×7B（MoE）：47B 总参数，13B 激活参数

结论：Mixtral 的"知识容量"接近 47B 模型，
      但推理计算量只相当于 13B 模型！
```

### 内存 vs 计算的权衡

```
MoE 的代价：

显存需求：需要加载所有专家的权重
  Mixtral 8×7B FP16：~94 GB（需要多卡）
  Mixtral 8×7B INT4：~24 GB（单张 RTX 4090 可运行）

计算量：只有激活专家参与前向传播
  推理速度接近同等激活参数量的密集模型
```

## MoE vs 密集模型

```
对比维度：

                密集模型          MoE 模型
参数效率        ████████          ████████████████
推理速度        ████████████      ████████████
显存需求        ████              ████████████████
训练稳定性      ████████████████  ████████
部署复杂度      ████              ████████████
```

### MoE 的优势

1. **参数效率高**：相同计算量下，MoE 可以拥有更多参数，"记住"更多知识
2. **推理速度快**：激活参数量少，前向传播计算量小
3. **扩展性好**：增加专家数量可以提升能力，而不显著增加推理成本

### MoE 的挑战

1. **显存需求大**：所有专家权重都需要加载到显存
2. **训练不稳定**：需要精心设计负载均衡策略
3. **通信开销**：多 GPU 部署时，不同专家可能在不同 GPU 上，需要 all-to-all 通信

## 代表性 MoE 模型

### Mixtral 8×7B（Mistral AI）

```
架构参数：
  专家数量：8
  每次激活：2
  总参数：~47B
  激活参数：~13B
  上下文长度：32K

特点：
  - 首个广泛使用的开源 MoE 大模型
  - 在多项基准上超越 Llama-2-70B
  - 有指令微调版本 Mixtral 8×7B Instruct
```

### DeepSeek-V2（DeepSeek）

```
架构参数：
  总专家数：160
  每次激活：6（2 共享 + 4 路由）
  总参数：236B
  激活参数：21B
  上下文长度：128K

创新点：
  - MLA（Multi-head Latent Attention）：压缩 KV Cache
  - 细粒度专家分割：更多更小的专家
  - 共享专家：部分专家始终激活，处理通用知识
```

### DeepSeek-Coder-V2

DeepSeek-V2 架构的代码专用版本，是 Delphi 支持的替代模型之一：

```
DeepSeek-Coder-V2-Lite：
  总参数：16B
  激活参数：2.4B
  专家数：64
  每次激活：6
  
特点：
  - 激活参数仅 2.4B，推理极快
  - 代码能力接近 GPT-4 Turbo（HumanEval 基准）
  - 支持 338 种编程语言
  - 可在 8GB 显存的 GPU 上运行（INT4 量化）
```

## MoE 推理的实现细节

### 专家并行（Expert Parallelism）

当模型太大无法放入单 GPU 时，可以将不同专家分布到不同 GPU：

```
4 GPU 部署 Mixtral 8×7B：

GPU 0：Expert 0, Expert 1
GPU 1：Expert 2, Expert 3
GPU 2：Expert 4, Expert 5
GPU 3：Expert 6, Expert 7

每个 token 路由到对应 GPU 上的专家
需要 all-to-all 通信收集结果
```

### vLLM 对 MoE 的支持

vLLM 对 MoE 模型有专门优化：

- 融合的 MoE kernel（FusedMoE），减少 kernel 启动开销
- 支持 Tensor Parallelism + Expert Parallelism 混合并行
- AWQ/GPTQ 量化支持，大幅降低显存需求

## Delphi 中的 MoE 模型

### DeepSeek-Coder-V2-Lite 作为替代模型

对于代码相关的知识库（如内部 API 文档、代码库问答），Delphi 推荐使用 DeepSeek-Coder-V2-Lite：

```yaml
# Delphi 配置：使用 DeepSeek-Coder-V2-Lite
model:
  backend: vllm
  name: deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct
  quantization: awq
  
  # MoE 模型推荐配置
  tensor_parallel_size: 1   # 激活参数少，单卡即可
  gpu_memory_utilization: 0.85
```

### 选择建议

```
知识库类型 → 推荐模型：

通用文档问答    → Qwen2.5-7B-Instruct（密集，稳定）
代码/技术文档   → DeepSeek-Coder-V2-Lite（MoE，代码能力强）
多语言内容      → Qwen2.5-7B-Instruct（多语言支持好）
资源极度受限    → Qwen2.5-3B-Instruct（密集，最小）
```

MoE 模型在代码理解和生成任务上通常优于同等激活参数量的密集模型，因为更多的专家可以"专门化"处理不同的编程语言和代码模式。

## 延伸阅读

- [Mixtral 技术报告](https://arxiv.org/abs/2401.04088)
- [DeepSeek-V2 技术报告](https://arxiv.org/abs/2405.04434)
- [Switch Transformers（Google MoE 奠基论文）](https://arxiv.org/abs/2101.03961)
- [vLLM MoE 优化博客](https://blog.vllm.ai/2024/01/04/vllm-v0.3.html)
