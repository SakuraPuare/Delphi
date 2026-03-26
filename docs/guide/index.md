# 项目简介

Delphi 是一款可离线部署的本地知识库系统。导入代码仓库、技术文档、音视频，即可获得基于 RAG（检索增强生成）的智能问答能力。

## 核心特性

- **多源数据导入**：Git 仓库（代码）、Markdown/HTML/PDF 文档、音视频文件
- **代码级理解**：基于 AST 的语法感知切分，不是暴力按行截断
- **离线运行**：全部组件本地部署，不依赖任何外部 API
- **模型可插拔**：内置默认模型，也支持导入自己微调的模型
- **一键部署**：Docker Compose 启动，开箱即用

## 使用场景

- 企业内部代码库知识问答
- 开源项目深度学习与探索（如大型 C++ / Java / Python 项目）
- 技术文档 + 视频教程的统一检索
- 团队知识沉淀与共享

## 技术栈概览

| 角色 | 选型 |
|------|------|
| LLM 推理 | vLLM + Qwen2.5-Coder-32B |
| Embedding | BGE-M3 |
| Reranker | BGE-Reranker-v2-M3 |
| 向量数据库 | Qdrant |
| 代码解析 | Tree-sitter |
| 音视频转录 | Faster-Whisper |
| RAG 框架 | LlamaIndex |
| 容器编排 | Docker Compose |
