# 推理引擎

## 选型策略

| 阶段 | 引擎 | 说明 |
|------|------|------|
| 开发调试 | Ollama | 开箱即用，`ollama run` 一条命令 |
| 生产部署 | vLLM | PagedAttention，高并发吞吐 |

两者都暴露 OpenAI 兼容 API，RAG 层代码无需修改即可切换。

## vLLM

### 核心优势

**PagedAttention**：传统推理框架中，KV Cache 因长度不可预估而预分配大块连续显存，浪费率高达 50%+。PagedAttention 借鉴操作系统虚拟内存分页思想，将 KV Cache 划分为固定大小的物理块按需分配，显存浪费率接近零。

效果：同等显存下，并发请求吞吐量提升 2~4 倍。

**Continuous Batching**：不等一个 batch 全部完成再处理下一个，而是动态地将新请求插入正在运行的 batch 中，最大化 GPU 利用率。

### 部署配置

```bash
# 单卡部署 Qwen2.5-Coder-32B（AWQ 量化）
vllm serve Qwen/Qwen2.5-Coder-32B-Instruct-AWQ \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.85 \
  --port 8001

# 双卡部署（如有 2× RTX 4090）
vllm serve Qwen/Qwen2.5-Coder-32B-Instruct \
  --tensor-parallel-size 2 \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.90 \
  --port 8001
```

### 关键参数

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `tensor-parallel-size` | 张量并行 GPU 数 | 等于 GPU 数量 |
| `max-model-len` | 最大上下文长度 | 32768（单卡）/ 65536（双卡） |
| `gpu-memory-utilization` | 显存使用比例 | 0.85~0.90 |
| `max-num-seqs` | 最大并发序列数 | 根据显存调整 |

### LoRA 热加载

vLLM 支持在运行时加载 LoRA adapter，无需重启服务：

```bash
vllm serve base-model \
  --enable-lora \
  --lora-modules custom-lora=/path/to/adapter
```

## Ollama

开发阶段使用，快速验证 RAG 效果：

```bash
# 安装
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull qwen2.5-coder:32b

# 启动（自动暴露 OpenAI 兼容 API）
ollama serve
```

API 端点：`http://localhost:11434/v1/chat/completions`

## Embedding 推理

BGE-M3 通过独立进程运行，不占用 LLM 的 GPU 显存：

- GPU 模式：使用 sentence-transformers 或 FlagEmbedding，占用约 2GB 显存
- CPU 模式：速度较慢但可用，适合 GPU 显存紧张时

推荐将 Embedding 模型部署在 CPU 上或使用 GPU 的少量显存，将主要显存留给 LLM。
