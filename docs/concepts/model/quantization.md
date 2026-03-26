# 模型量化 (Quantization)

量化是将模型权重从高精度浮点数压缩为低精度整数的技术，是在消费级硬件上运行大型语言模型的关键手段。

## 什么是量化？

神经网络的权重默认以 32 位浮点数（FP32）存储。量化通过降低每个参数的位宽来减少内存占用：

```
精度层级（从高到低）：

FP32  ████████████████████████████████  32 位 / 参数  ~4 字节
FP16  ████████████████                  16 位 / 参数  ~2 字节
INT8  ████████                           8 位 / 参数  ~1 字节
INT4  ████                               4 位 / 参数  ~0.5 字节
```

以一个 7B 参数模型为例：

| 精度  | 显存占用 | 典型硬件需求         |
|-------|----------|----------------------|
| FP32  | ~28 GB   | A100 80G             |
| FP16  | ~14 GB   | RTX 3090 / A10       |
| INT8  | ~7 GB    | RTX 3080 / RTX 4070  |
| INT4  | ~3.5 GB  | RTX 3060 / M2 Mac    |

## 为什么要量化？

### 内存节省

量化最直接的收益是显存占用大幅下降。INT4 量化相比 FP16 节省约 75% 的显存，使得原本需要多卡才能运行的模型可以在单张消费级显卡上部署。

### 推理加速

低精度整数运算在现代 GPU/CPU 上有专用硬件加速路径：

- INT8 矩阵乘法在 NVIDIA Ampere 架构上比 FP16 快约 2×
- INT4 在支持的硬件上可进一步提速
- CPU 推理（如 llama.cpp）对 INT4/INT8 有高度优化的 SIMD 指令

### 精度损失

量化不是免费的午餐。位宽越低，模型精度损失越大：

```
精度损失示意（以 MMLU 基准为例，7B 模型）：

FP16  ████████████████████  基准线 ~63%
INT8  ███████████████████░  损失 < 0.5%
INT4  ██████████████████░░  损失 1-2%
INT3  ████████████████░░░░  损失 3-5%（通常不可接受）
```

## 量化类型

### PTQ（训练后量化，Post-Training Quantization）

在已训练好的模型上直接应用量化，无需重新训练。流程简单，是目前最主流的方式：

```
原始模型 (FP16)
      │
      ▼
  校准数据集（少量样本）
      │
      ▼
  计算量化参数（scale, zero-point）
      │
      ▼
量化模型 (INT4/INT8)
```

优点：速度快，无需 GPU 集群，几分钟到几小时即可完成。
缺点：对极低位宽（INT3 以下）效果较差。

### QAT（量化感知训练，Quantization-Aware Training）

在训练过程中模拟量化误差，让模型"适应"低精度表示：

```
训练循环：
  前向传播 → 模拟量化 → 计算损失 → 反向传播（全精度梯度）
```

优点：精度损失更小，尤其在极低位宽下表现更好。
缺点：需要完整训练流程，计算成本高，通常只有模型厂商才会做。

## 主流量化格式

### GPTQ

由论文 *GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers* 提出。

- 逐层量化，利用 Hessian 矩阵信息最小化量化误差
- 支持 INT4/INT3/INT2
- 广泛用于 HuggingFace 生态，配合 `auto-gptq` 库使用
- 适合 GPU 推理

```bash
# 典型 GPTQ 模型命名
TheBloke/Llama-2-7B-GPTQ
```

### AWQ（Activation-aware Weight Quantization）

MIT 提出的改进方案，关键洞察：**不是所有权重都同等重要**。

- 识别对激活值影响大的"显著权重"，对其保留更高精度
- 比 GPTQ 在相同位宽下精度更高
- 推理速度更快（专用 CUDA kernel）
- **vLLM 原生支持 AWQ**，是 Delphi 的首选格式

```bash
# 典型 AWQ 模型命名
Qwen/Qwen2.5-7B-Instruct-AWQ
```

### GGUF（GPT-Generated Unified Format）

llama.cpp 项目定义的文件格式，前身为 GGML。

- 单文件包含模型权重、分词器、元数据
- 支持多种量化级别：Q2_K、Q4_K_M、Q5_K_M、Q8_0 等
- 专为 CPU 推理优化，也支持 GPU offload
- **Ollama 使用 GGUF 格式**，是 Delphi CPU 部署路径的基础

```
GGUF 量化级别对比（7B 模型）：

Q4_K_M  ████████████████████  ~4.1 GB  推荐平衡点
Q5_K_M  █████████████████████  ~4.8 GB  更高精度
Q8_0    ████████████████████████  ~7.7 GB  接近 FP16
```

## 质量与大小的权衡

实际选择量化级别时，需要根据硬件和任务要求综合考量：

```
决策树：

可用显存 < 6GB?
  ├─ 是 → INT4 (AWQ/GGUF Q4)，接受 1-2% 精度损失
  └─ 否 → 显存 < 12GB?
           ├─ 是 → INT8 或 Q5/Q6，精度损失 < 0.5%
           └─ 否 → FP16，无精度损失
```

对于 RAG 知识库场景（Delphi 的核心用例），INT4 量化通常已经足够，因为：
1. 检索增强本身会提供大量上下文，对模型"记忆"依赖较少
2. 推理任务（而非创作）对精度要求相对宽松
3. 吞吐量和延迟往往比极致精度更重要

## Delphi 中的量化实践

Delphi 根据部署后端自动选择量化策略：

### vLLM 后端（GPU 部署）

Delphi 推荐使用 AWQ 量化模型配合 vLLM：

```yaml
# Delphi 配置示例
model:
  backend: vllm
  name: Qwen/Qwen2.5-7B-Instruct-AWQ
  quantization: awq
```

vLLM 对 AWQ 有原生 kernel 支持，在 RTX 4090 上运行 7B AWQ 模型可达到约 80 tokens/s 的生成速度。

### Ollama 后端（CPU/混合部署）

Ollama 使用 GGUF 格式，Delphi 会自动拉取对应量化版本：

```yaml
# Delphi 配置示例
model:
  backend: ollama
  name: qwen2.5:7b-instruct-q4_K_M
```

推荐在 Apple Silicon Mac 上使用 Q4_K_M 或 Q5_K_M，Metal GPU 加速可将速度提升至 30-50 tokens/s。

## 延伸阅读

- [GPTQ 论文](https://arxiv.org/abs/2210.17323)
- [AWQ 论文](https://arxiv.org/abs/2306.00978)
- [llama.cpp GGUF 格式说明](https://github.com/ggerganov/llama.cpp/blob/master/docs/gguf.md)
- [vLLM 量化文档](https://docs.vllm.ai/en/latest/quantization/supported_hardware.html)
