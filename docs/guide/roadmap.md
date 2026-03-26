# 技术路线图

Delphi 的开发分为四个阶段，从最小可用产品出发，逐步扩展数据来源、优化检索质量、提升使用体验，最终迈向进阶的 Agentic 能力。

---

## Phase 1：MVP（最小可用产品）

### 目标与定位

端到端跑通完整的 RAG 流程。用户能够将一个代码仓库导入 Delphi，并通过自然语言对其进行问答。这一阶段的核心是验证技术路径的可行性，而非追求功能完备。

预期效果：能对一个中型代码仓库（如 10 万行 C++ 项目）进行有效问答。

### 功能列表

- [ ] Docker Compose 编排，一键启动完整服务栈（vLLM + Qdrant + BGE-M3 + API 服务）
- [ ] Git 仓库导入流程：`clone` → Tree-sitter AST 解析 → Chunk 切分 → Embedding → 入库
- [ ] Markdown 文档导入流程：解析 → 按标题切分 → Embedding → 入库
- [ ] 基础 RAG Pipeline：Query → Embedding → 向量检索 → Prompt 组装 → LLM 生成
- [ ] Open WebUI 接入作为对话前端
- [ ] CLI 工具：`delphi import` / `delphi query`
- [ ] 基础错误处理与日志输出

### 涉及技术组件

| 组件 | 用途 |
|------|------|
| vLLM | 本地 LLM 推理服务 |
| Qdrant | 向量数据库，存储与检索 Embedding |
| BGE-M3 | 文本 Embedding 模型 |
| LlamaIndex | RAG 流程编排框架 |
| Tree-sitter | 代码 AST 解析，结构化切分 |
| FastAPI | API 服务层 |
| Docker Compose | 服务编排与本地部署 |

### 关联概念文档

- [RAG（检索增强生成）](/concepts/core/rag) — 理解整体流程的核心概念
- [Embedding（文本嵌入）](/concepts/core/embedding) — Embedding 模型的工作原理
- [向量数据库](/concepts/core/vector-database) — Qdrant 的存储与检索机制
- [Chunking（文本切分）](/concepts/data/chunking) — 如何将文档切分为合适的片段
- [Tree-sitter](/concepts/data/tree-sitter) — 基于 AST 的代码解析
- [vLLM](/concepts/tools/vllm) — 高性能本地推理引擎
- [BGE-M3](/concepts/tools/bgem3) — 多语言、多粒度 Embedding 模型
- [LlamaIndex](/concepts/tools/llamaindex) — RAG 编排框架
- [Qdrant](/concepts/tools/qdrant) — 向量数据库服务
- [Docker Compose](/concepts/tools/docker-compose) — 本地服务编排
- [Prompt Engineering](/concepts/core/prompt-engineering) — Prompt 组装策略

### 预期产出

- 可运行的 Docker Compose 配置
- 支持代码仓库与 Markdown 文档的导入脚本
- 可用的 CLI 工具与 API 接口
- 基础问答能力验证

---

## Phase 2：数据增强与检索优化

### 目标与定位

在 MVP 基础上，扩展支持的数据来源，并通过 Reranker、混合检索等手段显著提升检索质量。这一阶段的重点是让 Delphi 能处理更多类型的知识，并给出更准确的答案。

### 功能列表

- [ ] 音视频转录导入（基于 Faster-Whisper，支持 `.mp4`、`.mp3`、`.wav` 等格式）
- [ ] PDF 文档导入（文本提取 + 按页/段落切分）
- [ ] HTML 网页导入（正文提取 + 结构化切分）
- [ ] Reranker 精排（BGE-Reranker-v2-M3），对向量检索结果二次排序
- [ ] Chunk 元数据丰富化（记录依赖关系、函数调用链、所属模块等）
- [ ] 增量更新机制（基于文件 hash，仅重新处理变更文件）
- [ ] 混合检索（Dense 向量检索 + Sparse 稀疏检索 + 关键词全文检索）
- [ ] 检索结果去重与合并

### 涉及技术组件

| 组件 | 用途 |
|------|------|
| Faster-Whisper | 音视频语音转录 |
| BGE-Reranker-v2-M3 | 检索结果精排 |
| Qdrant Sparse Vectors | 稀疏向量支持混合检索 |
| PyMuPDF / pdfplumber | PDF 文本提取 |
| BeautifulSoup / Trafilatura | HTML 正文提取 |

### 关联概念文档

- [Reranker（重排序）](/concepts/core/reranker) — 精排模型的原理与作用
- [混合检索](/concepts/core/hybrid-search) — Dense + Sparse 混合检索策略
- [Whisper（语音识别）](/concepts/data/whisper) — 音视频转录技术
- [Chunking（文本切分）](/concepts/data/chunking) — 不同数据类型的切分策略
- [Tokenization（分词）](/concepts/data/tokenization) — 文本预处理基础

### 预期产出

- 支持音视频、PDF、HTML 的导入管道
- 集成 Reranker 的增强检索流程
- 增量更新机制，避免重复处理
- 混合检索接口，检索准确率显著提升

---

## Phase 3：体验优化

### 目标与定位

在检索能力稳定后，聚焦于用户体验的全面提升。包括更智能的查询处理、可追溯的引用来源、流畅的多轮对话，以及自建的 Web 前端，摆脱对 Open WebUI 的依赖。

### 功能列表

- [ ] Query 改写（将模糊问题转化为更精确的检索查询）
- [ ] 意图路由（区分代码问答、文档问答、通用问答等场景）
- [ ] 引用溯源：回答中标注来源文件路径、行号，代码片段高亮展示
- [ ] 多轮对话支持（对话历史管理，上下文感知的追问）
- [ ] 自建 Web 前端（React，支持 SSE 流式输出）
- [ ] 多项目管理（在同一 Delphi 实例中管理多个独立知识库）
- [ ] 会话历史持久化

### 涉及技术组件

| 组件 | 用途 |
|------|------|
| React | 自建 Web 前端框架 |
| SSE（Server-Sent Events） | 流式输出，逐 token 显示回答 |
| FastAPI | 流式 API 接口 |
| SQLite / PostgreSQL | 会话历史与项目元数据持久化 |

### 关联概念文档

- [LLM（大语言模型）](/concepts/core/llm) — 理解流式生成与上下文窗口
- [Context Window（上下文窗口）](/concepts/core/context-window) — 多轮对话的上下文管理
- [Prompt Engineering](/concepts/core/prompt-engineering) — Query 改写与意图路由的 Prompt 设计
- [RAG（检索增强生成）](/concepts/core/rag) — 引用溯源的实现基础

### 预期产出

- 独立的 Web 前端，支持流式对话与引用展示
- Query 改写与意图路由模块
- 多项目管理界面与 API
- 完整的多轮对话体验

---

## Phase 4：进阶能力

### 目标与定位

在核心 RAG 能力成熟后，探索更高阶的应用场景：自动生成微调数据、支持自定义模型、实现多步推理的 Agentic RAG，以及与开发者工具链的深度集成。

### 功能列表

- [ ] 微调数据自动生成（基于知识库内容自动构造问答对）
- [ ] 自定义模型导入（支持 LoRA adapter 加载与权重合并）
- [ ] Agentic RAG（多步推理：分解问题 → 多次检索 → 综合回答）
- [ ] 工具调用支持（让 LLM 能主动触发代码搜索、文件读取等操作）
- [ ] VS Code 插件 / Continue.dev 集成（在 IDE 内直接问答）
- [ ] 代码关系图谱（函数调用图、模块依赖图可视化）
- [ ] 知识库质量评估工具（自动评测检索准确率与回答质量）

### 涉及技术组件

| 组件 | 用途 |
|------|------|
| LoRA | 参数高效微调，加载自定义适配器 |
| vLLM LoRA 支持 | 动态加载 LoRA adapter 进行推理 |
| LangGraph / LlamaIndex Agents | Agentic 多步推理编排 |
| Tree-sitter | 代码关系图谱的 AST 基础 |
| VS Code Extension API | IDE 插件开发 |
| Continue.dev | 开源 IDE AI 助手集成 |

### 关联概念文档

- [LoRA（低秩适配）](/concepts/model/lora) — 自定义模型微调与加载
- [量化（Quantization）](/concepts/model/quantization) — 自定义模型的部署优化
- [vLLM](/concepts/tools/vllm) — LoRA adapter 的动态加载支持
- [Tree-sitter](/concepts/data/tree-sitter) — 代码图谱的解析基础
- [RAG（检索增强生成）](/concepts/core/rag) — Agentic RAG 的扩展方向
- [MoE（混合专家模型）](/concepts/model/moe) — 进阶模型架构参考
- [PagedAttention](/concepts/model/paged-attention) — 长上下文推理的内存优化

### 预期产出

- 微调数据生成流水线
- LoRA adapter 管理与加载接口
- Agentic RAG 原型，支持多步推理
- VS Code 插件或 Continue.dev 集成
- 代码调用关系可视化

---

## 阶段总览

| 阶段 | 核心目标 | 关键里程碑 |
|------|----------|------------|
| Phase 1 | 端到端 RAG 跑通 | 代码仓库可导入并问答 |
| Phase 2 | 数据与检索增强 | 多数据源 + Reranker + 混合检索 |
| Phase 3 | 体验全面提升 | 自建前端 + 引用溯源 + 多轮对话 |
| Phase 4 | 进阶与生态集成 | Agentic RAG + IDE 插件 + 自定义模型 |
