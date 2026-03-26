# 大语言模型 (LLM) 基础

大语言模型（Large Language Model，LLM）是现代 AI 应用的核心组件。理解 LLM 的工作原理，有助于你更好地配置和使用 Delphi。

## 什么是大语言模型

大语言模型是一种基于海量文本数据训练的神经网络模型，能够理解和生成自然语言。"大"体现在两个维度：

- **参数规模**：从数十亿到数千亿个可学习参数
- **训练数据**：通常使用数 TB 甚至数十 TB 的文本语料

LLM 的核心能力是**下一个 token 预测**：给定一段文本，预测最可能出现的下一个词（或子词）。这个看似简单的任务，在足够大的规模下，涌现出了推理、代码生成、多语言理解等复杂能力。

## Transformer 架构

现代 LLM 几乎都基于 Transformer 架构（Vaswani et al., 2017）。其核心机制是**自注意力（Self-Attention）**：

```
输入序列: ["Delphi", "是", "一个", "RAG", "系统"]
         ↓
  自注意力层：每个 token 关注序列中所有其他 token
         ↓
  前馈网络层：对每个位置独立变换
         ↓
输出：每个位置的上下文感知表示
```

自注意力允许模型在处理每个词时，动态地关注输入序列中任意位置的信息，这解决了 RNN 难以捕捉长距离依赖的问题。

典型的 Decoder-only Transformer（GPT 系列、Qwen、Llama 等）结构：

```
Token Embedding
      ↓
[Transformer Block] × N
  ├── RMSNorm
  ├── Multi-Head Attention (因果掩码)
  ├── RMSNorm
  └── Feed-Forward Network (SwiGLU)
      ↓
LM Head (线性层 → Softmax → 词表概率分布)
```

## 训练阶段：预训练、微调与 RLHF

### 预训练（Pre-training）

在海量无标注文本上进行自监督学习，目标是预测下一个 token。这一阶段赋予模型语言理解和世界知识，但模型输出往往不符合人类对话习惯。

### 指令微调（Instruction Fine-tuning / SFT）

使用高质量的指令-回答对数据集，让模型学会遵循指令、以对话形式回答问题。这一步将"预测下一个词"的模型转变为"有用的助手"。

### RLHF（基于人类反馈的强化学习）

通过人类标注者对模型输出进行排序，训练一个奖励模型，再用强化学习（通常是 PPO）优化 LLM，使其输出更符合人类偏好。这是 ChatGPT 等模型表现出色的关键。

```
预训练基座模型
    ↓ SFT
指令跟随模型
    ↓ RLHF / DPO
对齐后的对话模型（如 Qwen2.5-Coder-Instruct）
```

## 关键参数

### 模型规模（Model Size）

以参数量衡量，常见规格：1.5B、7B、14B、32B、72B。更大的模型通常能力更强，但推理速度更慢、显存占用更高。

| 规模 | 典型显存需求（FP16） | 适用场景 |
|------|---------------------|---------|
| 7B   | ~14 GB              | 消费级 GPU，快速响应 |
| 14B  | ~28 GB              | 平衡性能与速度 |
| 32B  | ~64 GB              | 高质量输出，需要专业 GPU |
| 72B  | ~144 GB             | 接近闭源模型水平 |

### 上下文窗口（Context Window）

模型单次能处理的最大 token 数。详见 [上下文窗口](./context-window.md)。

### 温度（Temperature）

控制输出的随机性，范围通常为 0.0 ~ 2.0：

- `temperature=0`：确定性输出，每次生成相同结果，适合代码生成
- `temperature=0.7`：平衡创造性与准确性，适合问答
- `temperature=1.5`：高随机性，适合创意写作

### Top-p（核采样）

从累积概率达到 p 的最小 token 集合中采样。`top_p=0.9` 意味着只从概率最高的那些 token 中选择，直到它们的概率之和达到 90%。通常与 temperature 配合使用。

## 开源 vs 闭源模型

| 维度 | 开源模型 | 闭源模型 |
|------|---------|---------|
| 数据隐私 | 本地部署，数据不出境 | 数据发送至第三方 |
| 成本 | 一次性硬件投入 | 按 token 计费 |
| 可定制性 | 可微调、量化 | 受限于 API |
| 能力上限 | 略低于最强闭源模型 | GPT-4o、Claude 等领先 |
| 离线使用 | 支持 | 不支持 |

Delphi 专为本地部署设计，因此默认使用开源模型。

## 主流开源模型

### Qwen 系列（阿里云）

- **Qwen2.5**：通用能力强，中文表现优秀
- **Qwen2.5-Coder**：专为代码任务优化，支持 92 种编程语言
- **Qwen2.5-Math**：数学推理专项模型

### DeepSeek 系列

- **DeepSeek-V3**：性能接近 GPT-4o，开源权重
- **DeepSeek-R1**：强化学习推理模型，擅长复杂推理

### Llama 系列（Meta）

- **Llama 3.1/3.2/3.3**：英文能力强，生态丰富
- 中文能力相对 Qwen 较弱

### Mistral 系列

- **Mistral 7B / Mixtral 8x7B**：欧洲团队，注重效率
- MoE（混合专家）架构，推理效率高

## 为什么 Delphi 默认使用 Qwen2.5-Coder

Delphi 是面向代码知识库的 RAG 系统，默认模型选择 `Qwen2.5-Coder-7B-Instruct` 基于以下考量：

1. **代码理解能力**：在 HumanEval、MBPP 等代码基准上表现领先同规模模型
2. **中文支持**：原生支持中文，适合中文注释和文档的代码库
3. **上下文长度**：支持 128K token 上下文，适合大文件检索
4. **本地部署友好**：7B 规模在消费级 GPU（如 RTX 3080 10GB）上可流畅运行
5. **指令跟随**：Instruct 版本经过对齐，能准确理解 RAG 提示词格式

你可以在 `config.yaml` 中切换为其他模型：

```yaml
llm:
  model: qwen2.5-coder:7b  # 通过 Ollama 加载
  base_url: http://localhost:11434
  temperature: 0.1          # 代码问答建议低温度
  context_window: 32768
```

## 延伸阅读

- [分词与 Token](../data/tokenization.md)
- [上下文窗口](./context-window.md)
- [Attention Is All You Need（原始论文）](https://arxiv.org/abs/1706.03762)
