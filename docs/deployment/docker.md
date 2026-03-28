# Docker Compose 部署

## 服务组成

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `vllm` | vllm/vllm-openai | 8001 | LLM 推理引擎 |
| `qdrant` | qdrant/qdrant | 6333, 6334 | 向量数据库 |
| `embedding` | 自建 | 8002 | BGE-M3 Embedding 服务 |
| `reranker` | 自建 | 8003 | BGE-Reranker 服务 |
| `api` | 自建 | 8000 | RAG API 服务 |
| `web` | 自建 React 前端 | 3001 | Web 前端 |

## docker-compose.yml 结构

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  vllm:
    image: vllm/vllm-openai:latest
    ports:
      - "8001:8000"
    volumes:
      - ./models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    command: >
      --model /models/Qwen2.5-Coder-32B-Instruct-AWQ
      --max-model-len 32768
      --gpu-memory-utilization 0.85

  embedding:
    build: ./services/embedding
    ports:
      - "8002:8002"
    volumes:
      - ./models:/models

  reranker:
    build: ./services/reranker
    ports:
      - "8003:8003"
    volumes:
      - ./models:/models

  api:
    build: ./services/api
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
      - vllm
      - embedding
      - reranker
    environment:
      - QDRANT_URL=http://qdrant:6333
      - VLLM_URL=http://vllm:8000
      - EMBEDDING_URL=http://embedding:8002
      - RERANKER_URL=http://reranker:8003

  web:
    build: ./services/web
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  qdrant_data:
```

## 启动

```bash
# 首次启动（会构建自定义镜像）
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止
docker compose down

# 停止并清除数据
docker compose down -v
```

## 模型下载

首次部署前需要下载模型权重：

```bash
# 创建模型目录
mkdir -p models

# 下载 LLM（约 20GB）
huggingface-cli download Qwen/Qwen2.5-Coder-32B-Instruct-AWQ --local-dir models/Qwen2.5-Coder-32B-Instruct-AWQ

# 下载 Embedding（约 2.2GB）
huggingface-cli download BAAI/bge-m3 --local-dir models/bge-m3

# 下载 Reranker（约 1.1GB）
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir models/bge-reranker-v2-m3
```

离线环境下，在有网络的机器上下载后拷贝到部署机。

## GPU 分配策略

单卡场景（RTX 4090 24GB）：

| 服务 | GPU 显存 |
|------|---------|
| vLLM (LLM) | ~20GB |
| Embedding (BGE-M3) | CPU 运行 |
| Reranker | CPU 运行 |

双卡场景：

| 服务 | GPU |
|------|-----|
| vLLM (LLM) | GPU 0 |
| Embedding + Reranker | GPU 1 |
