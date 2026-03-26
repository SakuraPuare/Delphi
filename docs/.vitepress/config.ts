import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Delphi',
  description: '可离线部署的本地知识库系统',
  lang: 'zh-CN',
  base: '/Delphi/',

  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '指南', link: '/guide/' },
      { text: '架构', link: '/architecture/' },
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
