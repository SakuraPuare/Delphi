# LoRA 与 QLoRA 微调

LoRA（Low-Rank Adaptation）是目前最主流的大模型高效微调方法，让开发者用消费级硬件对数十亿参数的模型进行领域适配。

## 问题：全量微调代价高昂

传统的全量微调（Full Fine-tuning）需要更新模型的所有参数：

```
7B 模型全量微调资源需求：

参数量：7,000,000,000
FP16 权重：~14 GB
优化器状态（Adam）：~56 GB（权重的 4×）
梯度：~14 GB
激活值：~10-20 GB（取决于 batch size）

总计：~100 GB+ 显存
需要：8× A100 80G 或更多
```

对于大多数开发者和企业来说，这完全不现实。

## LoRA 的核心思想

LoRA 基于一个关键观察：**微调过程中权重的变化量是低秩的**。

### 低秩分解

对于一个预训练权重矩阵 `W`（维度 `d × k`），全量微调会学习一个更新量 `ΔW`：

```
全量微调：W' = W + ΔW
           W: d×k 矩阵，需要更新 d×k 个参数
```

LoRA 将 `ΔW` 分解为两个小矩阵的乘积：

```
LoRA：ΔW = B × A
      A: r×k 矩阵（r << d）
      B: d×r 矩阵

参数量：d×r + r×k = r×(d+k)  远小于 d×k
```

其中 `r` 是秩（rank），通常取 4、8、16 或 32。

### 直观理解

```
原始权重矩阵 W (1024×1024 = 1,048,576 参数)
         ┌─────────────────────┐
         │                     │
         │    预训练权重 W      │  冻结，不更新
         │                     │
         └─────────────────────┘
                    +
         ┌────┐   ┌─────────────────────┐
         │    │   │                     │
         │ B  │ × │         A           │  只训练这两个小矩阵
         │    │   │                     │
         └────┘   └─────────────────────┘
        1024×8        8×1024
        = 8,192 + 8,192 = 16,384 参数
        节省比例：98.4%
```

### 训练与推理

训练时，`W` 被冻结，只有 `A` 和 `B` 接收梯度更新。`B` 初始化为全零，`A` 用随机高斯初始化，确保训练开始时 `ΔW = 0`。

推理时，可以将适配器合并回原始权重，零额外开销：

```
W_merged = W + α/r × B×A
```

其中 `α` 是缩放因子（lora_alpha），控制适配器的影响强度。

## LoRA 的实际收益

以 7B 模型为例：

| 方法       | 可训练参数 | 显存需求 | 训练速度 |
|------------|------------|----------|----------|
| 全量微调   | 7B (100%)  | ~100 GB  | 基准     |
| LoRA r=8   | ~20M (0.3%)| ~16 GB   | 快 2-3×  |
| LoRA r=16  | ~40M (0.6%)| ~18 GB   | 快 2×    |

单张 RTX 3090 (24GB) 即可微调 7B 模型，RTX 4090 可舒适运行 13B 模型的 LoRA 训练。

## QLoRA：更进一步

QLoRA（Quantized LoRA）由 Tim Dettmers 等人在 2023 年提出，将量化与 LoRA 结合：

```
QLoRA 架构：

基础模型（4-bit NF4 量化，冻结）
         +
LoRA 适配器（BF16 精度，可训练）
         +
双重量化（对量化常数再次量化）
         +
分页优化器（处理显存峰值）
```

### NF4 量化

QLoRA 使用专为正态分布权重设计的 NF4（Normal Float 4）格式，比普通 INT4 精度更高。

### QLoRA 的收益

```
7B 模型 QLoRA 训练：

显存占用：~10 GB（可在 RTX 3080 上运行！）
精度损失：相比 BF16 LoRA < 1%
训练速度：比全量微调快 4-5×
```

这使得在单张 16GB 显卡上微调 13B 模型成为可能。

## 何时选择 LoRA vs 全量微调

```
决策指南：

数据量 < 10万条？
  └─ 是 → LoRA（数据少时全量微调容易过拟合）

硬件 < 4× A100？
  └─ 是 → LoRA/QLoRA（硬件限制）

任务是领域适配/风格调整？
  └─ 是 → LoRA 通常足够

需要改变模型基础能力（如学习新语言）？
  └─ 是 → 考虑全量微调

生产环境需要极致性能？
  └─ 是 → 全量微调后蒸馏，或 LoRA 合并后量化
```

## 实践指南

### 数据格式

LoRA 微调通常使用对话格式（ChatML 或 Alpaca 格式）：

```json
// ChatML 格式（推荐）
{
  "messages": [
    {"role": "system", "content": "你是一个专业的代码助手。"},
    {"role": "user", "content": "如何用 Python 读取 JSON 文件？"},
    {"role": "assistant", "content": "使用 `json` 模块：\n```python\nimport json\nwith open('file.json') as f:\n    data = json.load(f)\n```"}
  ]
}
```

```json
// Alpaca 格式（简单任务）
{
  "instruction": "将以下文本翻译成英文",
  "input": "今天天气很好",
  "output": "The weather is very nice today."
}
```

### 关键超参数

```python
# 典型 LoRA 配置
lora_config = {
    "r": 16,              # 秩，越大容量越强但参数越多
    "lora_alpha": 32,     # 缩放因子，通常设为 r 的 2×
    "target_modules": [   # 应用 LoRA 的层
        "q_proj", "v_proj",           # 最小配置
        # "k_proj", "o_proj",         # 更完整
        # "gate_proj", "up_proj", "down_proj"  # 全覆盖
    ],
    "lora_dropout": 0.05, # 防止过拟合
    "bias": "none",
}
```

### 训练工具

**Unsloth**（推荐，速度最快）：

```bash
pip install unsloth
```

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-7B-Instruct",
    max_seq_length=4096,
    load_in_4bit=True,  # QLoRA
)
model = FastLanguageModel.get_peft_model(model, r=16, lora_alpha=32)
```

Unsloth 通过手写 Triton kernel 将训练速度提升 2-5×，显存减少 60%。

**PEFT + TRL**（HuggingFace 官方方案）：

```bash
pip install peft trl transformers
```

```python
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer

lora_config = LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"])
model = get_peft_model(base_model, lora_config)
trainer = SFTTrainer(model=model, train_dataset=dataset, ...)
trainer.train()
```

### 导出适配器

训练完成后，适配器保存为独立文件（约几十到几百 MB）：

```
output/
├── adapter_config.json    # LoRA 配置
├── adapter_model.safetensors  # 适配器权重
└── tokenizer/             # 分词器文件
```

## Delphi 中的 LoRA 支持

Delphi 提供完整的 LoRA 工作流集成：

### 导出训练数据

Delphi 可以将知识库中的问答对、文档摘要导出为标准训练格式：

```bash
# 从 Delphi 知识库导出训练数据
delphi export-training-data \
  --format chatml \
  --output ./training_data.jsonl \
  --knowledge-base my-kb
```

这让你可以用知识库内容微调模型，使其更好地理解领域术语和回答风格。

### 加载 LoRA 适配器

训练完成后，将适配器导入 Delphi：

```yaml
# Delphi 配置
model:
  backend: vllm
  name: Qwen/Qwen2.5-7B-Instruct
  lora_adapters:
    - name: domain-adapter
      path: /path/to/adapter
      scale: 1.0  # 适配器强度，0-2 之间
```

vLLM 支持动态加载多个 LoRA 适配器，可以在不同请求间切换，无需重新加载模型。

## 延伸阅读

- [LoRA 原始论文](https://arxiv.org/abs/2106.09685)
- [QLoRA 论文](https://arxiv.org/abs/2305.14314)
- [Unsloth 文档](https://docs.unsloth.ai/)
- [PEFT 文档](https://huggingface.co/docs/peft)
- [vLLM LoRA 支持](https://docs.vllm.ai/en/latest/models/lora.html)
