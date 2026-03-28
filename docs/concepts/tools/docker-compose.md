# Docker Compose 容器编排

## 什么是 Docker 与容器化

**Docker** 是一种将应用程序及其所有依赖（运行时、库、配置文件）打包进一个独立单元（**容器**）的技术。容器与宿主机共享操作系统内核，但彼此之间完全隔离，具有以下优势：

- **环境一致性**：开发、测试、生产环境完全相同，消除"在我机器上能跑"的问题
- **快速启动**：容器启动时间通常在秒级，远快于虚拟机
- **资源高效**：无需为每个应用运行完整的操作系统
- **易于分发**：镜像可推送至 Docker Hub 或私有仓库，一条命令即可拉取运行

### 容器 vs 虚拟机

```
┌─────────────────────────────────────────────┐
│              虚拟机（VM）                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  App A   │  │  App B   │  │  App C   │  │
│  │  Libs    │  │  Libs    │  │  Libs    │  │
│  │  Guest OS│  │  Guest OS│  │  Guest OS│  │
│  └──────────┘  └──────────┘  └──────────┘  │
│              Hypervisor                      │
│              Host OS                         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│              容器（Container）               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  App A   │  │  App B   │  │  App C   │  │
│  │  Libs    │  │  Libs    │  │  Libs    │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│              Docker Engine                   │
│              Host OS（共享内核）              │
└─────────────────────────────────────────────┘
```

## Docker Compose：多容器编排

单个 `docker run` 命令只能管理一个容器。真实应用往往由多个服务组成（Web 服务器、数据库、缓存、消息队列……），**Docker Compose** 正是为此而生。

Docker Compose 通过一个 `docker-compose.yml` 文件声明式地定义整个应用栈，然后用一条命令启动、停止、重建所有服务：

```bash
docker compose up -d    # 后台启动所有服务
docker compose down     # 停止并移除所有容器
docker compose logs -f  # 实时查看所有服务日志
```

## 核心概念

### Services（服务）

每个服务对应一个容器，定义其镜像、端口映射、环境变量等：

```yaml
services:
  api:
    image: delphi-api:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/delphi
```

### Networks（网络）

Compose 默认为所有服务创建一个共享网络，服务之间可以直接用服务名互相访问（内置 DNS 解析）：

```yaml
# api 服务可以通过 http://qdrant:6333 访问 qdrant 服务
# 无需知道容器的实际 IP 地址
networks:
  delphi-net:
    driver: bridge
```

### Volumes（数据卷）

容器本身是无状态的，数据卷用于持久化存储，确保容器重启后数据不丢失：

```yaml
volumes:
  qdrant-data:    # 向量数据库数据
  model-cache:    # 下载的 AI 模型文件
```

## GPU 直通：NVIDIA Container Toolkit

在 AI 应用中，GPU 加速至关重要。通过 **NVIDIA Container Toolkit**，容器可以直接访问宿主机的 GPU：

```yaml
services:
  whisper:
    image: delphi-whisper:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all          # 或指定数量，如 count: 1
              capabilities: [gpu]
```

安装前提：

1. 宿主机已安装 NVIDIA 驱动
2. 安装 `nvidia-container-toolkit` 包
3. 重启 Docker daemon

验证 GPU 是否可用：

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

## 健康检查与依赖管理

### 健康检查（Health Check）

定义容器的健康状态检测逻辑，避免依赖服务在未就绪时就被调用：

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s   # 启动后等待 60s 再开始检测
```

### 依赖管理（depends_on）

```yaml
services:
  api:
    depends_on:
      qdrant:
        condition: service_healthy   # 等待 qdrant 健康后再启动
```

`condition: service_healthy` 比简单的 `depends_on` 更可靠，后者只等待容器启动，不等待服务就绪。

## 与 Kubernetes 的对比

| 维度 | Docker Compose | Kubernetes |
|------|---------------|------------|
| 学习曲线 | 低，YAML 简单直观 | 高，概念繁多 |
| 部署规模 | 单机或少量节点 | 大规模集群 |
| 高可用 | 有限支持 | 原生支持 |
| 自动扩缩容 | 不支持 | 支持 |
| 运维复杂度 | 低 | 高 |
| 适用场景 | 本地开发、小型部署 | 生产级大规模服务 |

对于 Delphi 这类**本地部署的个人/团队知识库**，Kubernetes 的复杂性远超实际需求。Docker Compose 提供了恰到好处的编排能力，同时保持了极低的运维门槛。

## Delphi 如何使用 Docker Compose

Delphi 的完整服务栈通过一个 `docker-compose.yml` 文件管理：

```
┌─────────────────────────────────────────────────────┐
│                   Delphi 服务栈                      │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  前端     │  │  API     │  │  Worker          │  │
│  │ (Nginx)  │  │ (FastAPI)│  │ (文档处理/转录)   │  │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│       │             │                  │             │
│  ┌────▼─────────────▼──────────────────▼─────────┐  │
│  │              delphi-net（内部网络）             │  │
│  └────┬─────────────┬──────────────────┬─────────┘  │
│       │             │                  │             │
│  ┌────▼─────┐  ┌────▼─────┐  ┌────────▼─────────┐  │
│  │  Qdrant  │  │  vLLM   │  │  TEI             │  │
│  │ (向量库) │  │ (LLM)   │  │  (Embedding)     │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

一条命令即可启动整个系统：

```bash
docker compose up -d
```

所有服务的数据均通过命名卷持久化，GPU 资源按需分配给需要推理加速的 Worker 服务。
