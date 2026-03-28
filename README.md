<div align="center">
  <img src="logo.webp" alt="Delphi Logo" width="200">
  <h1>Delphi</h1>
  <p>可离线部署的本地知识库系统</p>
  <p>导入代码仓库、技术文档、音视频，即可获得基于 RAG 的智能问答能力</p>
  <p>
    <a href="https://sakurapuare.github.io/Delphi/">📖 文档</a>
  </p>
</div>

---

## 核心特性

- **多源数据导入**：Git 仓库（代码）、Markdown/HTML/PDF 文档、音视频文件
- **代码级理解**：基于 AST 的语法感知切分，不是暴力按行截断
- **离线运行**：全部组件本地部署，不依赖任何外部 API
- **模型可插拔**：内置默认模型，也支持导入自己微调的模型
- **一键部署**：Docker Compose 启动，开箱即用

## 使用场景

- 企业内部代码库知识问答
- 开源项目深度学习与探索（如 Apollo、Linux Kernel 等大型 C++ 项目）
- 技术文档 + 视频教程的统一检索
- 团队知识沉淀与共享

---

## 架构概览

```
用户 ──→ Web UI / IDE 插件 / API
              │
         RAG 编排层
         ┌────┼────┐
     Query改写  Reranker  Prompt模板
              │
      ┌───────┼───────┐
   Qdrant    vLLM    BGE-M3
   向量库    LLM推理  Embedding
              │
         数据导入层
      ┌───────┼───────┐
  Tree-sitter  Whisper  文档解析器
  代码解析     音视频    MD/HTML/PDF
```

全部组件通过 Docker Compose 编排。

---

## 技术选型

### 模型

| 角色 | 默认模型 | 说明 |
|------|---------|------|
| LLM | Qwen3.5-27B | 单卡 24GB 可跑，128K 上下文 |
| Embedding | BGE-M3 | 1024 维，Dense + Sparse 双输出，中英文混合 |
| Reranker | BGE-Reranker-v2-M3 | 交叉编码器，~560M 参数，CPU 可跑 |
| 音视频转录 | Faster-Whisper large-v3 | INT8 量化，离线转录 |

用户可替换为任意 HuggingFace 格式 / GGUF 格式的模型。

### 基础设施

| 组件 | 选型 | 理由 |
|------|------|------|
| 向量数据库 | Qdrant | 单二进制部署，百万级数据 P95 < 30ms |
| 推理引擎 | vLLM（生产）/ Ollama（开发） | PagedAttention 高并发 |
| 代码解析 | Tree-sitter | 增量 AST 解析，多语言支持 |
| 容器编排 | Docker Compose | 一键启动全部服务 |

---

## 数据导入

### 支持的数据源

| 数据源 | 处理方式 | 切分策略 |
|--------|---------|---------|
| Git 仓库 | Tree-sitter AST 解析 | 函数/类/方法级别，附带文件路径、签名等元数据 |
| Markdown | 直接解析 | 按标题层级，保留层级路径 |
| HTML | 转 Markdown | 同上 |
| PDF | 文本提取 | 按段落/页面 |
| 音视频 | Faster-Whisper 转录 | 按时间窗口，附时间戳 |

### 代码语言支持

通过 Tree-sitter grammar 扩展，默认支持：C++、Python、Java、Go、Rust、JavaScript/TypeScript、Protobuf 等。

### 构建系统文件处理

许多大型项目有自己的构建系统和工具链（如 Bazel、CMake、Meson），构建配置文件中编码了模块间依赖关系、组件注册、代码生成规则等信息，这些是纯源码解析无法获取的。

处理策略：
- BUILD / .bzl / CMakeLists.txt 等构建文件作为普通 Chunk 索引（Tree-sitter 支持 Starlark/CMake 语法）
- 提取 `deps` 字段中的依赖关系作为元数据，丰富代码 Chunk 的上下文
- 项目自有的 CLI 工具文档（如 Apollo 的 `aem`、`buildtool`）作为文档类数据导入

### 增量更新

基于文件 hash 检测变更，仅重新处理变更部分，无需全量重建。

---

## 硬件要求

系统仅需推理能力，训练/微调在外部完成后导入权重即可。

| 组件 | 最低要求 | 推荐配置 |
|------|---------|---------|
| GPU | 1× 16GB 显存 | 1× RTX 4090 (24GB) |
| CPU | 8 核 | 16+ 核 |
| 内存 | 32GB | 64GB~128GB |
| 磁盘 | 500GB SSD | 2TB NVMe |

使用更小的模型（7B）时，16GB 显存即可运行。

---

## 微调支持

Delphi 本身不负责训练，但提供完整的微调工作流支持：

1. **数据生成**：从已导入的知识库中自动生成 Q&A 训练数据
2. **外部微调**：用户在自己的训练环境（云端 GPU / 本地多卡）完成 QLoRA / 全量微调
3. **模型导入**：将微调后的权重（LoRA adapter 或合并权重）放入模型目录，系统自动加载

---

## 前端

| 阶段 | 方案 |
|------|------|
| 定制 | 自建 Web UI（React + SSE，代码高亮、引用溯源） |
| 进阶 | VS Code 插件 / Continue.dev 集成 |

---

## 实施路线

### Phase 1：MVP
- [x] Docker Compose 编排（vLLM + Qdrant + BGE-M3）
- [x] 数据导入：Git 仓库 + 文档目录
- [x] Tree-sitter 代码切分 + 文档切分
- [x] 基础 RAG Pipeline
- [x] 自建前端（React + SSE）

### Phase 2：数据增强
- [x] 音视频转录导入
- [x] Chunk 元数据丰富化
- [x] Reranker 精排
- [x] 增量更新

### Phase 3：体验优化
- [x] Query 改写与意图路由
- [x] 引用溯源（来源文件 + 行号）
- [x] 多轮对话
- [x] 自建前端

### Phase 4：进阶
- [x] 微调数据自动生成
- [x] 自定义模型导入
- [x] Agentic RAG（多步推理）
- [x] IDE 插件
- [x] 代码关系图谱（Tree-sitter AST + 图存储）
