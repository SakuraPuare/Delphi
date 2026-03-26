# vLLM 推理引擎

vLLM 是由加州大学伯克利分校开发的高性能大语言模型推理与服务框架，专为生产环境下的 LLM 部署而设计。它通过一系列创新技术显著提升了推理吞吐量，是目前开源社区中最主流的 LLM 推理引擎之一。

## 为什么需要 vLLM

传统 LLM 推理框架面临两个核心瓶颈：

1. **KV Cache 内存碎片化**：自回归生成过程中，每个 token 都需要缓存 Key/Value 矩阵。传统方案预先为每个请求分配固定大小的连续内存块，导致大量内存浪费（内部碎片）和无法复用（外部碎片）。
2. **低并发吞吐**：朴素实现下，GPU 在等待新 token 生成时大量时间处于空闲状态，批处理效率极低。

vLLM 通过 PagedAttention 和 Continuous Batching 从根本上解决了这两个问题。

## 核心特性

### PagedAttention

PagedAttention 借鉴操作系统虚拟内存分页的思想，将 KV Cache 切分为固定大小的"页"（block），通过逻辑块到物理块的映射表进行管理。

```
逻辑 KV Cache（请求视角）        物理 GPU 显存
┌─────────────────────┐         ┌──────────────┐
│ 请求 A: [B0][B1][B2]│ ──映射──▶│ 物理块 #3    │
│ 请求 B: [B0][B1]    │ ──映射──▶│ 物理块 #7    │
│ 请求 C: [B0]        │ ──映射──▶│ 物理块 #1    │
└─────────────────────┘         └──────────────┘
```

优势：
- 消除内存碎片，显存利用率提升至 ~96%
- 支持跨请求的 KV Cache 共享（Prefix Caching），相同前缀只需计算一次
- 动态按需分配，无需预估最大序列长度

### Continuous Batching

传统静态批处理需要等待批次内所有请求同时完成才能接受新请求。Continuous Batching（也称 iteration-level scheduling）在每个前向传播步骤后动态调度：

```
时间轴 →
静态批处理:  [请求A████████][请求B██][请求C████████████]  ← 等待最长请求
                                    ↑ GPU 空闲

连续批处理:  [请求A████████][请求D██████]
             [请求B██][请求C████████████]               ← 请求B完成后立即插入请求D
```

效果：GPU 利用率大幅提升，整体吞吐量提高 2-10 倍。

### Tensor Parallelism（张量并行）

对于超出单卡显存的大模型，vLLM 支持将模型权重按列/行切分到多张 GPU 上并行计算：

```
单卡 70B 模型（需 ~140GB）→ 不可行

4 卡张量并行：
GPU 0: 权重分片 0/4  ─┐
GPU 1: 权重分片 1/4  ─┤─ AllReduce ─▶ 完整输出
GPU 2: 权重分片 2/4  ─┤
GPU 3: 权重分片 3/4  ─┘
```

## OpenAI 兼容 API

vLLM 内置与 OpenAI API 完全兼容的 HTTP 服务，无需修改任何客户端代码即可替换 OpenAI：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="token-abc123",  # vLLM 不校验，填任意值即可
)

response = client.chat.completions.create(
    model="Qwen/Qwen2.5-7B-Instruct",
    messages=[{"role": "user", "content": "你好"}],
    temperature=0.7,
)
print(response.choices[0].message.content)
```

支持的端点：
- `POST /v1/chat/completions`（含流式 SSE）
- `POST /v1/completions`
- `POST /v1/embeddings`
- `GET /v1/models`

## 与其他方案对比

| 特性 | vLLM | llama.cpp | Ollama | TensorRT-LLM |
|------|------|-----------|--------|--------------|
| 主要场景 | 高并发服务 | 本地/边缘推理 | 开发者体验 | 极致性能 |
| PagedAttention | ✅ | ❌ | ❌ | ✅ |
| Continuous Batching | ✅ | 部分 | 部分 | ✅ |
| 多 GPU 支持 | ✅ | 有限 | ❌ | ✅ |
| CPU 推理 | ❌ | ✅ | ✅ | ❌ |
| 量化支持 | GPTQ/AWQ/FP8 | GGUF | GGUF | INT8/INT4 |
| 部署复杂度 | 中 | 低 | 极低 | 高 |
| OpenAI 兼容 | ✅ | 需插件 | ✅ | 需封装 |

**选择建议**：
- 需要高并发、多用户同时访问 → vLLM
- 个人笔记本、无 GPU → llama.cpp / Ollama
- 追求极致吞吐、有 NVIDIA 专业支持 → TensorRT-LLM

## 部署模式

### 单 GPU

```bash
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --port 8000 \
  --dtype auto \
  --max-model-len 8192
```

### 多 GPU（张量并行）

```bash
vllm serve meta-llama/Llama-3-70B-Instruct \
  --tensor-parallel-size 4 \
  --port 8000
```

### 多节点（Ray 集群）

```bash
# 主节点
ray start --head
# 工作节点
ray start --address=<head-node-ip>:6379
# 启动 vLLM（自动利用 Ray 集群）
vllm serve <model> --tensor-parallel-size 8 --pipeline-parallel-size 2
```

## 关键配置参数

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `--max-model-len` | 最大上下文长度（影响显存） | 按需设置，不超过模型支持上限 |
| `--gpu-memory-utilization` | GPU 显存占用比例 | `0.90`（留余量给系统） |
| `--tensor-parallel-size` | 张量并行卡数 | 与 GPU 数量一致 |
| `--quantization` | 量化方式 | `awq` 或 `gptq`（显存不足时） |
| `--enable-prefix-caching` | 启用前缀缓存 | `true`（RAG 场景强烈推荐） |
| `--max-num-seqs` | 最大并发序列数 | 根据显存调整，默认 256 |

## Delphi 如何使用 vLLM

Delphi 将 vLLM 作为 LLM 推理后端，通过其 OpenAI 兼容接口与 LlamaIndex 集成：

```
用户查询
   │
   ▼
LlamaIndex QueryEngine
   │  构造 prompt（含检索到的文档片段）
   ▼
vLLM（OpenAI 兼容端点）
   │  高效批处理推理
   ▼
生成回答（流式返回）
```

Delphi 特别利用了 vLLM 的以下能力：
- **Prefix Caching**：系统提示词（system prompt）在多轮对话中保持不变，vLLM 自动缓存其 KV Cache，降低首 token 延迟
- **流式输出**：通过 SSE 将生成内容实时推送到前端，提升用户体验
- **OpenAI SDK 兼容**：LlamaIndex 的 `OpenAI` LLM 适配器可直接指向本地 vLLM 端点，无需额外适配代码
