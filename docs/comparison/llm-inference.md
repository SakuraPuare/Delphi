# LLM 推理引擎对比

本文对主流 LLM 推理引擎进行横向对比，帮助你理解 Delphi 在不同场景下的引擎选择策略。

## 引擎概览

| 引擎 | 定位 | 开源协议 | 实现语言 |
|------|------|----------|----------|
| vLLM | 高吞吐量生产推理服务 | Apache 2.0 | Python / C++ |
| TensorRT-LLM | NVIDIA GPU 极致优化推理 | Apache 2.0 | C++ / Python |
| llama.cpp | CPU / 边缘设备推理 | MIT | C++ |
| Ollama | 本地开发友好的推理封装 | MIT | Go |
| SGLang | 结构化生成 + 高吞吐量 | Apache 2.0 | Python |
| TGI | HuggingFace 官方推理服务 | Apache 2.0 | Rust / Python |

---

## 多维度对比

| 维度 | vLLM | TensorRT-LLM | llama.cpp | Ollama | SGLang | TGI |
|------|------|-------------|-----------|--------|--------|-----|
| 吞吐量（tokens/s，A100） | ~3000 | ~5000 | ~200（CPU） | ~800 | ~3500 | ~2000 |
| 首 token 延迟 | 中 | 低 | 高 | 中 | 低 | 中 |
| 显存效率 | 高（PagedAttention） | 极高 | N/A | 中 | 高 | 中 |
| 量化支持 | AWQ / GPTQ / FP8 | INT4 / INT8 / FP8 | GGUF（Q2~Q8） | GGUF | AWQ / FP8 | GPTQ / AWQ |
| 模型格式 | HuggingFace | TensorRT Engine | GGUF | GGUF / HF | HuggingFace | HuggingFace |
| OpenAI API 兼容 | 是 | 部分 | 是（server 模式） | 是 | 是 | 是 |
| 部署难度 | 中 | 高 | 低 | 极低 | 中 | 中 |
| 多 GPU 支持 | 是（张量并行） | 是 | 有限 | 有限 | 是 | 是 |
| 适合场景 | 生产服务 | 极致性能生产 | 边缘 / 离线 | 本地开发 | 生产 + 结构化生成 | HF 生态生产 |

> 吞吐量数据基于 Llama-3-8B，batch size=32，A100 80GB，仅供参考。

---

## 各引擎详细分析

### vLLM

核心技术是 **PagedAttention**，将 KV Cache 分页管理，显著提升并发吞吐量。支持连续批处理（Continuous Batching），长短请求混合时性能优势明显。

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --tensor-parallel-size 2 \
  --max-model-len 8192
```

适合：生产环境、多并发用户、需要 OpenAI 兼容接口。

### TensorRT-LLM

NVIDIA 官方推理库，针对 NVIDIA GPU 深度优化，支持 FP8 精度和 In-Flight Batching。性能是所有方案中最高的，但需要将模型编译为 TensorRT Engine，流程复杂，模型更新成本高。

适合：对延迟和吞吐量要求极高、GPU 资源充足、模型版本稳定的生产场景。

### llama.cpp

纯 C++ 实现，支持 CPU 推理和 Apple Silicon Metal 加速。GGUF 格式支持 2-bit 到 8-bit 量化，在消费级硬件上可运行 7B 模型。

```bash
./llama-server -m qwen2.5-7b-instruct-q4_k_m.gguf --port 8080
```

适合：无 GPU 环境、边缘设备、离线场景。

### Ollama

基于 llama.cpp 封装，提供极简的模型管理和 API 服务。一条命令拉取并运行模型，内置 OpenAI 兼容接口。

```bash
ollama pull qwen2.5:7b
ollama serve  # 默认监听 localhost:11434
```

适合：本地开发、快速验证、非技术用户。

### SGLang

专为结构化生成（JSON Schema、函数调用）优化，引入 RadixAttention 提升前缀缓存命中率。在需要大量结构化输出的场景下吞吐量优于 vLLM。

适合：Agent 场景、大量工具调用、结构化输出需求强的生产环境。

### TGI（Text Generation Inference）

HuggingFace 官方推理服务，与 HF Hub 生态深度集成，支持 Flash Attention 2 和 Paged Attention。Rust 实现的 HTTP 服务层性能好，但定制化能力弱于 vLLM。

适合：已深度使用 HuggingFace 生态、需要快速部署 HF Hub 模型的团队。

---

## 场景推荐

### 开发环境

推荐 **Ollama**：
- 零配置，`ollama pull` 即可使用
- 自动管理模型文件，支持多模型切换
- 内置 OpenAI 兼容接口，与 LlamaIndex / LangChain 无缝对接
- 资源占用可控，不影响开发机其他工作

### 生产环境

推荐 **vLLM**：
- PagedAttention 在高并发下显存利用率比 Ollama 高 2-3 倍
- 连续批处理支持混合长度请求，P99 延迟更稳定
- 张量并行支持多 GPU 水平扩展
- 社区活跃，模型支持更新快

### 边缘 / 离线部署

推荐 **llama.cpp** 或 **Ollama**：
- llama.cpp 适合无 Docker 环境、资源极度受限的场景
- Ollama 适合有一定资源但希望简化运维的边缘节点

---

## Delphi 的引擎策略

Delphi 采用双引擎策略：

**开发阶段使用 Ollama**：
- `docker compose up` 一键启动，包含 Ollama 服务
- 默认拉取 `qwen2.5:7b` 和 `nomic-embed-text` 两个模型
- 通过环境变量 `LLM_BASE_URL=http://ollama:11434/v1` 切换

**生产阶段使用 vLLM**：
- 提供独立的 `docker-compose.prod.yml`，替换 Ollama 为 vLLM 服务
- 同样暴露 OpenAI 兼容接口，应用层代码无需修改
- 支持通过 `--tensor-parallel-size` 配置多 GPU

切换方式：

```bash
# 开发
docker compose up

# 生产（需要 NVIDIA GPU）
docker compose -f docker-compose.prod.yml up
```

两种模式下，Delphi 的 LlamaIndex 配置完全相同，仅 `base_url` 和 `model` 参数不同，通过环境变量注入。
