# 功能：Docker Compose 编排

## 功能描述

通过 Docker Compose 一键启动 Delphi 所需的全部服务，无需手动配置各组件的网络、依赖和环境变量。执行一条命令即可完成从模型加载到 Web 界面的完整部署。

## 服务清单

| 服务名 | 镜像 | 对外端口 | 说明 |
|--------|------|----------|------|
| `vllm` | `vllm/vllm-openai:latest` | `8000` | LLM 推理服务 |
| `qdrant` | `qdrant/qdrant:latest` | `6333`, `6334` | 向量数据库 |
| `embedding` | `ghcr.io/huggingface/text-embeddings-inference:latest` | `8080` | BGE-M3 嵌入服务 |
| `api` | `delphi/api:latest`（本地构建） | `8888` | FastAPI 后端 |
| `webui` | `ghcr.io/open-webui/open-webui:main` | `3000` | Web 前端 |

## 各服务配置详情

### vLLM 推理服务

```yaml
vllm:
  image: vllm/vllm-openai:latest
  ports:
    - "8000:8000"
  environment:
    - MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
    - MAX_MODEL_LEN=8192
    - TENSOR_PARALLEL_SIZE=1
  volumes:
    - ~/.cache/huggingface:/root/.cache/huggingface
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  command: >
    --model ${MODEL_NAME}
    --max-model-len ${MAX_MODEL_LEN}
    --tensor-parallel-size ${TENSOR_PARALLEL_SIZE}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 120s
```

详见概念文档：[vLLM](/concepts/tools/vllm)

### Qdrant 向量数据库

```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports:
    - "6333:6333"   # REST API
    - "6334:6334"   # gRPC
  volumes:
    - qdrant_data:/qdrant/storage
  environment:
    - QDRANT__SERVICE__GRPC_PORT=6334
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
    interval: 10s
    timeout: 5s
    retries: 3
```

详见概念文档：[Qdrant](/concepts/tools/qdrant)

### Embedding 服务（BGE-M3）

```yaml
embedding:
  image: ghcr.io/huggingface/text-embeddings-inference:latest
  ports:
    - "8080:80"
  environment:
    - MODEL_ID=BAAI/bge-m3
    - MAX_BATCH_TOKENS=16384
  volumes:
    - ~/.cache/huggingface:/data
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:80/health"]
    interval: 15s
    timeout: 5s
    retries: 5
    start_period: 60s
```

详见概念文档：[BGE-M3](/concepts/tools/bgem3)

### API Server（FastAPI）

```yaml
api:
  build: ./api
  ports:
    - "8888:8888"
  environment:
    - VLLM_BASE_URL=http://vllm:8000/v1
    - QDRANT_URL=http://qdrant:6333
    - EMBEDDING_URL=http://embedding:80
    - API_KEY=${DELPHI_API_KEY:-}
  depends_on:
    vllm:
      condition: service_healthy
    qdrant:
      condition: service_healthy
    embedding:
      condition: service_healthy
  volumes:
    - ./config.yaml:/app/config.yaml:ro
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8888/health"]
    interval: 10s
    timeout: 5s
    retries: 3
```

### Web UI（Open WebUI）

```yaml
webui:
  image: ghcr.io/open-webui/open-webui:main
  ports:
    - "3000:8080"
  environment:
    - OPENAI_API_BASE_URL=http://api:8888/v1
    - OPENAI_API_KEY=${DELPHI_API_KEY:-delphi}
    - WEBUI_AUTH=false
  volumes:
    - webui_data:/app/backend/data
  depends_on:
    api:
      condition: service_healthy
```

## 服务依赖关系与启动顺序

```
qdrant ──┐
          ├──► api ──► webui
embedding─┤
vllm ─────┘
```

各服务通过 `depends_on` + `condition: service_healthy` 保证按序启动，只有上游服务通过健康检查后，下游服务才会启动。

## GPU 资源分配策略

- `vllm` 和 `embedding` 各占用 1 块 GPU
- 若只有 1 块 GPU，可将两个服务的 `count` 均设为 `1`，通过 CUDA MPS 共享（需宿主机开启 MPS）
- 纯 CPU 模式：移除 `deploy.resources` 块，并在 vLLM 命令中添加 `--device cpu`（性能显著下降）

## 网络配置

所有服务默认加入同一个 bridge 网络 `delphi_net`，服务间通过服务名互相访问，无需暴露额外端口。

```yaml
networks:
  default:
    name: delphi_net
```

## 数据卷

```yaml
volumes:
  qdrant_data:    # Qdrant 持久化存储
  webui_data:     # Open WebUI 用户数据
```

## 首次启动流程

1. 复制环境变量文件：`cp .env.example .env`
2. 按需修改 `.env` 中的模型名称和 API Key
3. 执行启动命令：

```bash
docker compose up -d
```

4. 首次启动时，`vllm` 和 `embedding` 会自动从 Hugging Face 下载模型权重（约 15-30 分钟，取决于网络）
5. 查看启动日志：

```bash
docker compose logs -f vllm embedding
```

6. 所有服务就绪后，访问 `http://localhost:3000` 打开 Web 界面

## 常用运维命令

```bash
# 停止所有服务（保留数据）
docker compose down

# 停止并清除所有数据卷
docker compose down -v

# 重启单个服务
docker compose restart api

# 查看服务状态
docker compose ps
```
