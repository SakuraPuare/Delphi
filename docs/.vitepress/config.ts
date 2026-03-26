import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Delphi',
  description: '可离线部署的本地知识库系统',
  lang: 'zh-CN',
  base: '/Delphi/',

  head: [['link', { rel: 'icon', href: '/Delphi/logo.webp' }]],

  themeConfig: {
    logo: '/logo.webp',

    nav: [
      { text: '首页', link: '/' },
      { text: '指南', link: '/guide/' },
      { text: 'MVP', link: '/mvp/' },
      { text: '架构', link: '/architecture/' },
      { text: '概念', link: '/concepts/core/rag' },
      { text: '对比', link: '/comparison/competitors' },
      { text: '部署', link: '/deployment/' },
    ],

    sidebar: {
      '/guide/': [
        {
          text: '指南',
          items: [
            { text: '项目简介', link: '/guide/' },
            { text: '快速开始', link: '/guide/quickstart' },
            { text: '数据导入', link: '/guide/data-import' },
            { text: '微调支持', link: '/guide/fine-tuning' },
            { text: '技术路线图', link: '/guide/roadmap' },
          ],
        },
      ],
      '/mvp/': [
        {
          text: 'MVP 版本',
          items: [
            { text: '概述', link: '/mvp/' },
            { text: 'Git 仓库导入', link: '/mvp/git-import' },
            { text: '文档目录导入', link: '/mvp/doc-import' },
            { text: '基础 RAG Pipeline', link: '/mvp/rag-pipeline' },
            { text: 'Docker Compose 编排', link: '/mvp/docker-setup' },
            { text: 'API 服务', link: '/mvp/api-server' },
            { text: 'CLI 命令行工具', link: '/mvp/cli' },
          ],
        },
      ],
      '/architecture/': [
        {
          text: '架构设计',
          items: [
            { text: '总览', link: '/architecture/' },
            { text: '数据处理流水线', link: '/architecture/data-pipeline' },
            { text: 'RAG 编排', link: '/architecture/rag' },
            { text: '模型选型', link: '/architecture/models' },
            { text: '向量数据库', link: '/architecture/vector-db' },
            { text: '推理引擎', link: '/architecture/inference' },
          ],
        },
      ],
      '/concepts/': [
        {
          text: '核心概念',
          items: [
            { text: '检索增强生成 (RAG)', link: '/concepts/core/rag' },
            { text: '大语言模型 (LLM)', link: '/concepts/core/llm' },
            { text: '向量嵌入 (Embedding)', link: '/concepts/core/embedding' },
            { text: '向量数据库', link: '/concepts/core/vector-database' },
            { text: '混合检索', link: '/concepts/core/hybrid-search' },
            { text: '重排序模型 (Reranker)', link: '/concepts/core/reranker' },
            { text: 'Prompt Engineering', link: '/concepts/core/prompt-engineering' },
            { text: '上下文窗口', link: '/concepts/core/context-window' },
            { text: 'SSE 流式传输', link: '/concepts/core/sse' },
            { text: 'RAG 评估指标', link: '/concepts/core/evaluation' },
            { text: 'OpenAI 兼容 API', link: '/concepts/core/openai-api' },
          ],
        },
        {
          text: '数据处理',
          items: [
            { text: '文本切分策略 (Chunking)', link: '/concepts/data/chunking' },
            { text: 'Tree-sitter 与 AST', link: '/concepts/data/tree-sitter' },
            { text: '分词与 Token', link: '/concepts/data/tokenization' },
            { text: 'Whisper 语音识别', link: '/concepts/data/whisper' },
            { text: '元数据与知识图谱', link: '/concepts/data/metadata' },
            { text: '增量更新机制', link: '/concepts/data/incremental-update' },
          ],
        },
        {
          text: '模型技术',
          items: [
            { text: '模型量化 (Quantization)', link: '/concepts/model/quantization' },
            { text: 'LoRA 与 QLoRA 微调', link: '/concepts/model/lora' },
            { text: 'PagedAttention 与推理优化', link: '/concepts/model/paged-attention' },
            { text: '混合专家模型 (MoE)', link: '/concepts/model/moe' },
          ],
        },
        {
          text: '工具与框架',
          items: [
            { text: 'vLLM 推理引擎', link: '/concepts/tools/vllm' },
            { text: 'Qdrant 向量数据库', link: '/concepts/tools/qdrant' },
            { text: 'LlamaIndex RAG 框架', link: '/concepts/tools/llamaindex' },
            { text: 'BGE-M3 嵌入模型', link: '/concepts/tools/bgem3' },
            { text: 'Docker Compose', link: '/concepts/tools/docker-compose' },
          ],
        },
      ],
      '/comparison/': [
        {
          text: '横向对比',
          items: [
            { text: '竞品分析', link: '/comparison/competitors' },
            { text: 'RAG 框架对比', link: '/comparison/rag-frameworks' },
            { text: '向量数据库对比', link: '/comparison/vector-databases' },
            { text: 'LLM 推理引擎对比', link: '/comparison/llm-inference' },
            { text: 'Embedding 模型对比', link: '/comparison/embedding-models' },
            { text: 'Reranker 模型对比', link: '/comparison/reranker-models' },
            { text: '代码解析方案对比', link: '/comparison/code-parsing' },
          ],
        },
      ],
      '/deployment/': [
        {
          text: '部署',
          items: [
            { text: '硬件要求', link: '/deployment/' },
            { text: 'Docker Compose 部署', link: '/deployment/docker' },
            { text: '配置说明', link: '/deployment/config' },
            { text: 'API 接口', link: '/deployment/api' },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/SakuraPuare/Delphi' },
    ],

    outline: {
      label: '目录',
    },

    docFooter: {
      prev: '上一页',
      next: '下一页',
    },
  },
})
