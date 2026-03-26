# 快速开始

## 环境要求

- Docker + Docker Compose
- NVIDIA GPU（≥ 16GB 显存）+ NVIDIA Container Toolkit
- 磁盘空间 ≥ 100GB（模型权重 + 向量索引）

## 一键启动

```bash
git clone https://github.com/SakuraPuare/Delphi.git
cd Delphi
docker compose up -d
```

首次启动会自动下载模型权重，耗时取决于网络速度。

## 导入数据

### 导入 Git 仓库

```bash
# 通过 CLI
delphi import git https://github.com/ApolloAuto/apollo.git

# 或导入本地仓库
delphi import git /path/to/your/repo
```

### 导入文档目录

```bash
delphi import docs /path/to/your/docs
```

### 导入音视频

```bash
delphi import media /path/to/videos/
```

## 开始问答

启动后访问 `http://localhost:3000` 进入 Web UI，即可开始提问。

也可以通过 API 调用：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "CyberRT 的组件注册机制是怎样的？"}'
```
