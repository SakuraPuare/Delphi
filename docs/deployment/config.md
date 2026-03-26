# 配置说明

Delphi 使用 YAML 配置文件，位于项目根目录的 `config.yaml`。

## 完整配置示例

```yaml
# LLM 配置
llm:
  model: Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
  base_url: http://localhost:8001/v1
  max_tokens: 4096
  temperature: 0.1
  # 可选：LoRA adapter 路径
  # lora_adapter: models/custom-lora/

# Embedding 配置
embedding:
  model: BAAI/bge-m3
  base_url: http://localhost:8002
  batch_size: 32
  device: cpu  # cpu / cuda

# Reranker 配置
reranker:
  model: BAAI/bge-reranker-v2-m3
  base_url: http://localhost:8003
  top_n: 5  # 精排后保留的 Chunk 数
  device: cpu

# 向量数据库配置
vector_db:
  url: http://localhost:6333
  collection: delphi_chunks
  vector_size: 1024
  distance: cosine

# 检索配置
retrieval:
  top_k: 20          # 初筛召回数量
  rerank_top_n: 5    # 精排后保留数量
  score_threshold: 0.3  # 最低相似度阈值
  enable_reranker: true

# 数据导入配置
import:
  # 代码解析
  code:
    max_chunk_tokens: 2000    # 单个 Chunk 最大 token 数
    languages:                 # 启用的语言
      - cpp
      - python
      - java
      - go
      - rust
      - javascript
      - typescript
      - protobuf
    include_build_files: true  # 是否索引 BUILD/CMake 文件
    exclude_patterns:          # 排除的文件模式
      - "**/*_test.cc"
      - "**/test/**"
      - "**/third_party/**"
      - "**/*.pb.cc"
      - "**/*.pb.h"

  # 文档解析
  docs:
    formats:
      - md
      - html
      - pdf
      - txt

  # 音视频转录
  media:
    model: large-v3
    language: auto    # auto / zh / en
    compute_type: int8
    chunk_duration: 30  # 秒

# 服务配置
server:
  host: 0.0.0.0
  port: 8000
  cors_origins:
    - "http://localhost:3000"
```

## 环境变量覆盖

所有配置项均可通过环境变量覆盖，格式为 `DELPHI_` 前缀 + 大写路径：

```bash
export DELPHI_LLM_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct
export DELPHI_VECTOR_DB_URL=http://qdrant:6333
export DELPHI_RETRIEVAL_TOP_K=30
```

## 多项目支持

Delphi 支持在同一实例中管理多个项目的知识库：

```bash
# 导入不同项目
delphi import git https://github.com/ApolloAuto/apollo.git --project apollo
delphi import git https://github.com/example/other.git --project other

# 查询时指定项目
delphi query "如何注册组件？" --project apollo
```

项目通过 Qdrant payload 中的 `project` 字段隔离。
