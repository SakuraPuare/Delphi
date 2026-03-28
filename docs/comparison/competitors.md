# 竞品分析与开源项目调研

> 本文梳理当前开源 RAG / 知识库 / 代码智能领域的主要项目，评估其与 Delphi 的重叠度，并明确 Delphi 的差异化定位。

---

## 1. 通用 RAG / 知识库平台

### RAGFlow（InfiniFlow）

- **简介**：基于深度文档理解的开源 RAG 引擎，核心模块 DeepDoc 可对 PDF、Word、表格、图片等进行结构化解析。
- **GitHub Stars**：~40k（2025 年初）
- **技术栈**：Python、Elasticsearch、MinIO、MySQL
- **核心特性**：可视化 chunk 预览、引用溯源、多种切分策略（naive / paper / book / table / picture 等）、支持 Agent 工作流
- **离线部署**：支持（Docker Compose 一键部署）
- **代码支持**：弱，无 AST 感知，代码文件按文本处理
- **优点**：文档解析能力业界领先，chunk 质量高，社区活跃
- **缺点**：重量级（依赖 ES + MinIO），代码仓库场景几乎未考虑，无音视频支持
- **可借鉴**：DeepDoc 的多模态文档解析思路；chunk 可视化预览 UI 设计

---

### Dify

- **简介**：面向 AI 应用开发的工作流平台，支持 RAG Pipeline、Agent、工作流编排。
- **GitHub Stars**：~80k（2025 年初）
- **技术栈**：Python（后端）、Next.js（前端）、PostgreSQL、Weaviate/Qdrant
- **核心特性**：可视化工作流编排、多模型切换、知识库管理、API 发布
- **离线部署**：支持（Docker）
- **代码支持**：弱，知识库以文档为主，无代码语义理解
- **优点**：生态最完整，插件市场丰富，工作流 UI 体验好
- **缺点**：定位是通用 AI 应用平台，不专注代码/技术文档场景；部署较重
- **可借鉴**：工作流编排 UI；多数据源连接器设计；API 网关层设计

---

### AnythingLLM

- **简介**：桌面端 + Docker 双模式的全能 AI 应用，支持本地 LLM、RAG、Agent。
- **GitHub Stars**：~35k
- **技术栈**：Node.js、SQLite、LanceDB（内置向量库）
- **核心特性**：Workspace 隔离、多文档格式支持、内置 Ollama 集成、Agent 工具调用
- **离线部署**：支持（桌面 App 或 Docker，开箱即用）
- **代码支持**：一般，可导入代码文件但无语义切分
- **优点**：部署极简，桌面 App 体验好，适合个人用户
- **缺点**：单机性能瓶颈，无代码 AST 理解，团队协作能力弱
- **可借鉴**：桌面 App 打包方案；Workspace 多项目隔离设计

---

### PrivateGPT

- **简介**：隐私优先的本地 RAG 系统，100% 离线运行，无数据外泄。
- **GitHub Stars**：~55k
- **技术栈**：Python、LlamaIndex、Qdrant/Chroma、Ollama
- **核心特性**：完全离线、REST API、支持多种本地模型后端
- **离线部署**：完全支持（设计目标即离线）
- **代码支持**：弱，文本切分，无代码感知
- **优点**：隐私保护彻底，架构简洁，API 设计清晰
- **缺点**：功能相对基础，UI 简陋，代码场景无优化
- **可借鉴**：离线优先的架构设计原则；LlamaIndex 集成方式

---

### Quivr

- **简介**："第二大脑"定位，支持多种文件格式上传并与 AI 对话。
- **GitHub Stars**：~37k
- **技术栈**：Python（FastAPI）、Next.js、Supabase（PostgreSQL + pgvector）
- **核心特性**：多文件格式、Brain 概念（知识空间）、分享与协作
- **离线部署**：部分支持（依赖 Supabase，本地化有一定门槛）
- **代码支持**：弱
- **优点**：UI 美观，Brain 概念直观，协作功能
- **缺点**：强依赖 Supabase，离线部署复杂；代码场景无优化；近期维护活跃度下降
- **可借鉴**：Brain / 知识空间的 UX 概念

---

### Danswer / Onyx

- **简介**：企业级知识搜索 + QA 平台，前身 Danswer，现更名 Onyx，已完成 $10M 融资。
- **GitHub Stars**：~15k
- **技术栈**：Python、PostgreSQL、Vespa（混合搜索）、Redis
- **核心特性**：40+ 数据源连接器（Slack、Confluence、GitHub 等）、混合搜索（BM25 + 向量）、知识图谱、权限同步
- **离线部署**：支持（Docker Compose）
- **代码支持**：中等，可接入 GitHub 仓库，但以文档/Issue 为主，无代码语义理解
- **优点**：企业集成能力强，混合搜索质量高，权限管理完善
- **缺点**：偏企业 SaaS 方向，代码理解深度不足，部署较重
- **可借鉴**：混合搜索（BM25 + 向量）架构；多数据源连接器抽象层

---

### Kotaemon

- **简介**：面向文档 QA 的开源 RAG UI 框架，强调引用溯源和可扩展性。
- **GitHub Stars**：~20k
- **技术栈**：Python、Gradio、LlamaIndex
- **核心特性**：多文档对话、引用高亮、可插拔 LLM/Embedding、支持本地模型
- **离线部署**：支持
- **代码支持**：弱
- **优点**：引用溯源 UI 体验好，架构清晰，易于二次开发
- **缺点**：Gradio UI 扩展性有限，代码场景无优化
- **可借鉴**：引用溯源的 UI 交互设计；可插拔组件架构

---

### MaxKB

- **简介**：国内 1Panel 团队出品的开源知识库问答系统，中文社区活跃。
- **GitHub Stars**：~15k
- **技术栈**：Python（Django）、PostgreSQL + pgvector、Vue.js
- **核心特性**：开箱即用、工作流编排、MCP 工具调用、多模型支持、可嵌入第三方系统
- **离线部署**：支持
- **代码支持**：弱，以文档知识库为主
- **优点**：中文文档完善，国内用户友好，部署简单，与 1Panel 生态集成
- **缺点**：代码场景无专项优化，音视频不支持
- **可借鉴**：中文本地化经验；嵌入式 Widget 设计；与运维平台集成的思路

---

### PandaWiki（长亭科技）

- **简介**：AI 大模型驱动的开源知识库搭建系统，定位为快速构建产品文档、技术文档、FAQ、博客系统，提供 AI 创作、AI 问答、AI 搜索能力。AGPL-3.0 许可证，另有闭源 Pro 版。
- **GitHub Stars**：~5k（2026 年初）
- **GitHub 仓库**：`timhuang2003/AINEWPROJECT`（fork / 镜像）
- **技术栈**：Go 1.24（后端，Echo v4 + GORM + Wire DI）、React 18 + Vite（管理后台）、Next.js 15 App Router（Wiki 前台）、PostgreSQL、Redis、NATS（消息队列）、MinIO（对象存储）、Caddy（反向代理）、pnpm monorepo
- **核心特性**：
  - AI 辅助创作 / 问答 / 搜索，基于 CloudWego Eino RAG SDK + ModelKit
  - ProseMirror 富文本编辑器，兼容 Markdown 和 HTML，支持导出 Word / PDF / Markdown
  - AI FIM（Fill-in-the-Middle）Tab 补全 + AI 文本润色 / 改写
  - Yjs 实时协同编辑（多人同时编辑同一文档）
  - 多来源内容导入：URL 抓取、Sitemap、RSS 订阅、Notion、飞书文档、Confluence、Epub、语雀、思源笔记、Mindoc、WikiJS、文件上传（独立 `panda-wiki-crawler` 微服务处理）
  - 第三方集成：网页挂件、钉钉 / 飞书 / 企业微信 / Discord 聊天机器人、微信公众号、企微客服
  - 多知识库隔离，每个知识库独立生成 Wiki 站点
  - OpenAI 兼容 API 输出（可作为任意 OpenAI SDK 客户端的 RAG 后端）
  - 细粒度节点权限：可见性 / 可访问性 / 可被 AI 回答 三维独立控制
  - 内容保护：复制限制（追加水印文本或禁用复制）、可见 / 隐形水印
  - 发布版本管理（类 Git tag 的版本标签机制）
  - 对话历史记录 + 内联引用溯源
  - 统计分析面板（1 / 7 / 30 / 90 天窗口，含 Geo-IP + UA 解析）
  - 认证：密码 / LDAP / OAuth2 / GitHub / CAS / 钉钉 / 飞书 / 企微 SSO
  - 可观测性：OpenTelemetry 分布式追踪 + Sentry 错误监控
  - 专业版额外支持多用户权限、组织管理、API Token
- **离线部署**：支持（Docker 一键安装脚本，多架构 amd64 + arm64），但 AI 模型需外部配置（推荐百智云或自建，DeepSeek 扩展集成）
- **代码支持**：弱，无 AST 感知，代码文件按文本处理，无 Git 仓库导入
- **优点**：
  - 产品化程度高，管理后台 + Wiki 前台双端完整，主题系统完善（12+ 预设主题）
  - 第三方 IM 集成最丰富（钉钉、飞书、企微、Discord、微信公众号、企微客服）
  - 内容导入源覆盖广（URL / Sitemap / RSS / Notion / 飞书 / Confluence / Epub / 语雀 / 思源 / WikiJS 等 12+ 来源）
  - Yjs 实时协同编辑，适合团队协作场景
  - Go 后端性能好，Clean Architecture 分层清晰
  - 细粒度权限 + 内容保护（水印）适合企业合规需求
  - 前端 monorepo 组件库独立封装（themes / icons / ui）
- **缺点**：
  - 无代码仓库导入和代码语义理解
  - 无音视频支持
  - AI 模型不内置，需用户自行配置第三方模型服务（DeepSeek / OpenAI 等）
  - 不支持离线推理（依赖外部 LLM API）
  - 无微调工作流
  - 部署组件较多（PostgreSQL + Redis + NATS + MinIO + Caddy + Crawler = 6 个外部依赖）
- **可借鉴**：
  - 网页挂件 / IM 机器人的多渠道分发设计
  - 12+ 内容导入源的 Crawler 微服务架构（独立进程，格式统一转 Markdown）
  - Yjs 协同编辑集成方案
  - 细粒度节点权限模型（可见 / 可访问 / 可回答 三维）
  - 内容保护机制（水印 + 复制限制）
  - Go 后端的 Clean Architecture 分层（domain → usecase → handler → repo）
  - 前端 monorepo 组件库（themes / icons / ui 独立 package）
  - OpenTelemetry + Sentry 可观测性方案

**与 Delphi 的核心差异**：

| 维度 | PandaWiki | Delphi |
|------|-----------|--------|
| 定位 | 通用知识库 / Wiki 站点生成器 | 代码优先的本地知识库 |
| 代码理解 | 无（纯文本处理） | AST 感知切分（Tree-sitter） |
| 数据源 | URL / Sitemap / RSS / Notion / Confluence 等 12+ 来源 | Git 仓库 / 文档 / 音视频 |
| 模型部署 | 依赖外部 API（DeepSeek / OpenAI） | 完全离线（vLLM 本地推理） |
| 微调 | 不支持 | 支持（数据生成 + 模型导入） |
| 音视频 | 不支持 | Whisper 转录 + 时间戳检索 |
| 图谱 | 不支持 | 代码关系图谱（Graph RAG） |
| 协同编辑 | Yjs 实时协同 | 不支持（单用户场景为主） |
| 内容导入 | 12+ 来源（Notion / Confluence / 飞书等） | Git clone + 文件上传 |
| 分发渠道 | Wiki 站点 + 6 种 IM 机器人 + 挂件 | Web UI / API / IDE 插件 |
| 权限体系 | 细粒度（可见 / 可访问 / 可回答）+ SSO | 基础（API Key） |
| 内容保护 | 水印 + 复制限制 | 无 |
| 后端语言 | Go | Python |
| 外部依赖 | 6 个（PG + Redis + NATS + MinIO + Caddy + Crawler） | 4 个（Qdrant + TEI + vLLM + 可选 Jaeger） |

**总结**：PandaWiki 在产品化、多渠道分发、内容导入广度、协同编辑和企业合规（权限 + 水印）上显著领先。但在代码理解、离线推理、模型自主性、音视频支持上与 Delphi 的设计目标完全不同。两者面向的用户群体有明显差异：PandaWiki 适合需要快速搭建产品文档站并对接多种 IM 渠道的团队，Delphi 适合需要深度理解代码仓库并完全离线运行的技术团队。

**Delphi 可从 PandaWiki 学习的方向**：
1. 多来源内容导入——Delphi 目前仅支持 Git 仓库和文件上传，可考虑增加 Confluence / Notion / 飞书文档等技术团队常用平台的导入
2. IM 机器人分发——技术团队也大量使用飞书 / Slack / Discord，将 RAG 问答能力推送到 IM 中可降低使用门槛
3. 内容保护机制——对于企业内网部署场景，水印和复制限制是合规刚需

---

## 2. 代码专用 RAG / 代码智能

### Sourcegraph Cody

- **简介**：Sourcegraph 出品的代码 AI 助手，深度集成代码搜索引擎，支持全仓库上下文。
- **开源情况**：客户端开源，服务端部分闭源
- **技术栈**：TypeScript、Go、Zoekt（代码搜索）
- **核心特性**：全仓库语义搜索、符号级上下文、多 IDE 插件、支持自托管
- **离线部署**：企业版支持自托管，社区版依赖云服务
- **代码支持**：极强，专为代码设计，理解符号引用、调用链
- **优点**：代码理解深度业界最强之一，与 Sourcegraph 搜索引擎协同
- **缺点**：完整自托管复杂，文档/音视频场景不支持
- **可借鉴**：符号级索引思路；代码搜索与 LLM 上下文的结合方式

---

### Continue.dev

- **简介**：开源 AI 代码助手 IDE 插件，支持 VS Code 和 JetBrains，可接入任意 LLM。
- **GitHub Stars**：~25k
- **技术栈**：TypeScript
- **核心特性**：`@codebase` 全仓库索引、本地 Ollama 集成、自定义上下文提供者、支持离线
- **离线部署**：完全支持（本地 LLM + 本地索引）
- **代码支持**：强，专为代码场景设计，支持 codebase 向量索引
- **优点**：IDE 集成体验好，完全开源，离线友好，社区活跃
- **缺点**：定位是 IDE 插件，不是独立知识库系统；文档/音视频场景不支持
- **可借鉴**：`@codebase` 索引实现；与 IDE 集成的接口设计；可作为 Delphi 的 IDE 前端集成方案

---

### Bloop

- **简介**：基于 Rust 的自然语言代码搜索引擎，支持语义搜索和代码问答。
- **状态**：已于 2025 年 1 月归档（repository archived），项目停止维护
- **技术栈**：Rust、Tree-sitter、Qdrant
- **核心特性**：Tree-sitter AST 解析、语义代码搜索、本地部署
- **离线部署**：支持
- **代码支持**：强，基于 AST 的代码理解
- **可借鉴**：Tree-sitter 集成方案（代码已开源，可直接参考）；Rust 实现的高性能索引思路

---

### Greptile

- **简介**：专注代码仓库的 RAG API 服务，将代码库视为图结构而非文件列表。
- **开源情况**：闭源 SaaS，有开源 SDK
- **技术栈**：未公开（图索引 + 向量检索）
- **核心特性**：仓库级图索引、依赖关系理解、API 接口
- **离线部署**：不支持（云服务）
- **代码支持**：极强，专为代码仓库设计
- **可借鉴**：将代码库建模为图（文件依赖图、调用图）的索引思路

---

### Aider

- **简介**：终端 AI 结对编程工具，支持多文件编辑，与 git 深度集成。
- **GitHub Stars**：~25k
- **技术栈**：Python
- **核心特性**：仓库地图（repo-map）、多文件编辑、git 自动提交、支持本地模型
- **离线部署**：支持
- **代码支持**：强，repo-map 基于 Tree-sitter 构建符号索引
- **可借鉴**：repo-map 的实现（轻量级符号索引，无需完整向量化）；与 git 集成的工作流

---

### Tabby

- **简介**：自托管 AI 编程助手，GitHub Copilot 的开源替代品。
- **GitHub Stars**：~25k
- **技术栈**：Rust（服务端）、TypeScript（插件）
- **核心特性**：代码补全、RAG 增强补全（本地仓库上下文）、多 IDE 支持、团队部署
- **离线部署**：完全支持（设计目标即自托管）
- **代码支持**：强，专为代码补全和代码问答设计
- **可借鉴**：Rust 实现的高性能代码索引服务；团队级自托管部署方案；可作为 Delphi 的代码补全前端

---

## 3. 综合对比表

| 项目 | 开源协议 | 离线部署 | 代码理解 | 文档支持 | 音视频 | AST 解析 | 自定义模型 | 部署复杂度 | 活跃度 |
|------|----------|----------|----------|----------|--------|----------|------------|------------|--------|
| RAGFlow | Apache 2.0 | ✅ | ❌ | ✅✅ | ❌ | ❌ | ✅ | 高 | 高 |
| Dify | Apache 2.0 | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | 高 | 极高 |
| AnythingLLM | MIT | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | 低 | 高 |
| PrivateGPT | Apache 2.0 | ✅✅ | ❌ | ✅ | ❌ | ❌ | ✅ | 低 | 中 |
| Quivr | Apache 2.0 | 部分 | ❌ | ✅ | ❌ | ❌ | ✅ | 中 | 低 |
| Onyx | MIT | ✅ | △ | ✅ | ❌ | ❌ | ✅ | 高 | 高 |
| Kotaemon | Apache 2.0 | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | 低 | 中 |
| MaxKB | Apache 2.0 | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | 低 | 高 |
| Sourcegraph Cody | Apache 2.0 | 部分 | ✅✅ | △ | ❌ | ✅ | △ | 高 | 高 |
| Continue.dev | Apache 2.0 | ✅ | ✅ | △ | ❌ | △ | ✅ | 低 | 高 |
| Bloop | Apache 2.0 | ✅ | ✅ | ❌ | ❌ | ✅ | △ | 低 | 已归档 |
| Greptile | 闭源 | ❌ | ✅✅ | ❌ | ❌ | ✅ | ❌ | — | 高 |
| Aider | Apache 2.0 | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | 低 | 极高 |
| Tabby | Apache 2.0 | ✅✅ | ✅ | ❌ | ❌ | △ | ✅ | 中 | 高 |
| **Delphi（目标）** | — | ✅✅ | ✅✅ | ✅ | ✅✅ | ✅✅ | ✅ | 中 | — |

> 说明：✅✅ = 核心优势，✅ = 支持，△ = 部分支持，❌ = 不支持

---

## 4. 可直接复用或借鉴的项目

### 4.1 直接 fork / 改造

目前没有高度匹配 Delphi 全部需求的单一项目，不建议 fork。原因：

- 通用 RAG 平台（RAGFlow、Dify）的代码理解能力几乎为零，改造成本等同重写
- 代码专用工具（Bloop、Tabby）不支持文档和音视频，扩展方向相反
- 最接近的是 **Continue.dev**，但它是 IDE 插件而非独立知识库服务

**结论：Delphi 应从头构建核心索引引擎，但可大量复用现有组件。**

### 4.2 借鉴架构设计

| 借鉴来源 | 借鉴内容 |
|----------|----------|
| RAGFlow | 多模态文档解析流水线；chunk 可视化预览 |
| Onyx | 混合搜索（BM25 + 向量）架构；多数据源连接器抽象 |
| Aider | repo-map 轻量符号索引；与 git 集成的工作流 |
| Greptile | 代码库图索引（文件依赖图 + 调用图）思路 |
| PrivateGPT | 离线优先架构原则；LlamaIndex 集成方式 |

### 4.3 可复用组件

| 组件 | 来源 | 用途 |
|------|------|------|
| Tree-sitter 绑定 | Bloop（已归档，代码可参考）、Aider | AST 解析与代码切分 |
| repo-map 实现 | Aider（`aider/repomap.py`） | 轻量级符号索引，快速构建仓库地图 |
| 文档解析 | RAGFlow DeepDoc | PDF/Word/表格的结构化解析 |
| 混合搜索 | Onyx / LlamaIndex | BM25 + 向量混合检索 |
| Whisper 集成 | 社区通用方案 | 音视频转录 |

### 4.4 集成使用

| 项目 | 集成方式 |
|------|----------|
| Continue.dev | 作为 IDE 插件前端，通过 Delphi API 提供 `@codebase` 上下文 |
| Tabby | 作为代码补全前端，Delphi 提供仓库级 RAG 上下文增强 |
| OpenAI 兼容客户端 | 通过 OpenAI 兼容 API 接入 Delphi |
| Ollama | 本地 LLM 推理后端 |

---

## 5. Delphi 的差异化定位

### 5.1 现有项目的共同盲区

经过调研，以下三个能力在现有开源项目中均未被完整实现：

**① 代码 AST 感知切分**
绝大多数通用 RAG 平台（RAGFlow、Dify、AnythingLLM、PandaWiki 等）将代码文件视为普通文本，按行数或字符数切分。这导致函数被截断、上下文丢失。Bloop 和 Aider 有 Tree-sitter 集成，但前者已停止维护，后者是编辑工具而非知识库。

**② 构建系统与依赖图理解**
没有任何开源项目能理解 `Cargo.toml`、`package.json`、`go.mod`、`CMakeLists.txt` 等构建文件，并将依赖关系纳入检索上下文。Greptile 声称有图索引，但是闭源 SaaS。

**③ 音视频 + 代码统一检索**
技术会议录像、架构讲解视频、代码 Review 录屏——这些内容与代码仓库高度相关，但没有任何现有系统将音视频转录内容与代码语义统一索引。RAGFlow 等通用平台不支持音视频，PandaWiki 等知识库平台同样不涉及，代码专用工具更不涉及。

### 5.2 Delphi 的独特价值主张

```
Delphi = 代码仓库 RAG（AST 感知）
       + 技术文档 RAG（结构化解析）
       + 音视频知识（Whisper 转录 + 时间戳检索）
       + 统一离线部署
```

与现有项目的核心差异：

1. **代码优先，而非文档优先**：索引粒度到函数/类/模块级别，而非文本块
2. **构建系统感知**：理解项目依赖关系，检索时可提供依赖上下文
3. **音视频原生支持**：技术视频与代码的跨模态检索（"这个函数在哪个视频里讲过？"）
4. **完全离线**：不依赖任何云服务，适合企业内网和敏感代码库

### 5.3 诚实评估：是否有项目已做到 90%？

**没有。** 最接近的组合是 Continue.dev（代码 RAG）+ RAGFlow（文档解析），但两者之间没有统一的检索层，也都不支持音视频。PandaWiki 在产品化和内容导入广度上做得最好（12+ 数据源、IM 机器人、协同编辑），但完全不涉及代码语义理解和音视频处理。Delphi 的核心创新在于**统一索引层**——将代码、文档、音视频的异构内容统一到一个可检索的知识图谱中。

这意味着 Delphi 需要自建核心，但可以大量复用现有组件（Tree-sitter、Whisper、LlamaIndex、混合搜索），避免重复造轮子。

### 5.4 Delphi 应向竞品学习的方向

| 学习方向 | 参考项目 | 说明 |
|----------|----------|------|
| 多来源内容导入 | PandaWiki | 12+ 数据源（Notion / Confluence / 飞书等），独立 Crawler 微服务架构 |
| IM 机器人分发 | PandaWiki | 飞书 / 钉钉 / 企微 / Discord / 微信公众号，降低使用门槛 |
| 内容保护 | PandaWiki | 水印 + 复制限制，企业合规刚需 |
| 协同编辑 | PandaWiki | Yjs 实时协同，适合团队场景 |
| 文档解析 | RAGFlow | DeepDoc 多模态文档解析，chunk 质量高 |
| 工作流编排 | Dify | 可视化 RAG Pipeline 编排 UI |
| 混合搜索 | Danswer/Onyx | BM25 + 向量融合架构 |
| 引用溯源 UI | Kotaemon | 引用高亮交互设计 |

---

*最后更新：2026-03-28*
