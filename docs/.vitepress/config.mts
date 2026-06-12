import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'zh-CN',
  title: 'DST Serverd',
  description: '饥荒联机版(Don\'t Starve Together)专用服务器管理系统 — 统一管理多个服务器分片和实例',

  // 部署到自定义域名根路径,base 保持默认 '/'
  base: '/',
  cleanUrls: true,
  lastUpdated: true,
  // 现有文档的锚点链接按 GitHub 规则书写,与 VitePress slug 略有差异,不因死链中断构建
  ignoreDeadLinks: true,
  // docs/README.md 仅作仓库内索引,站点首页由 index.md 提供
  srcExclude: ['README.md'],

  head: [
    ['link', { rel: 'icon', type: 'image/png', href: '/logo.png' }],
    ['meta', { name: 'theme-color', content: '#b3001b' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:title', content: 'DST Serverd 文档' }],
    ['meta', { property: 'og:description', content: '饥荒联机版专用服务器管理系统文档站' }],
  ],

  sitemap: {
    hostname: 'https://dst-serverd-wiki.dreamreflex.com',
  },

  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: '/logo.png',

    nav: [
      { text: '使用指南', link: '/guide' },
      { text: '技术架构', link: '/architecture' },
      { text: '手动部署', link: '/dst-server-setup' },
      {
        text: '更多',
        items: [
          { text: '打包与发布', link: '/release' },
          { text: 'GitHub 仓库', link: 'https://github.com/phil616/dst-server-icp' },
          { text: 'CNB 仓库', link: 'https://cnb.cool/greenshadecapital/dst-server-icp' },
        ],
      },
    ],

    sidebar: [
      {
        text: '开始使用',
        items: [
          { text: '项目简介', link: '/' },
          { text: '使用指南', link: '/guide' },
        ],
      },
      {
        text: '部署',
        items: [
          { text: '手动部署 DST 服务端', link: '/dst-server-setup' },
        ],
      },
      {
        text: '深入了解',
        items: [
          { text: '技术架构方案', link: '/architecture' },
        ],
      },
      {
        text: '维护',
        items: [
          { text: '打包与发布流程', link: '/release' },
        ],
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/phil616/dst-server-icp' },
    ],

    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
          modal: {
            noResultsText: '无法找到相关结果',
            resetButtonTitle: '清除查询条件',
            footer: {
              selectText: '选择',
              navigateText: '切换',
              closeText: '关闭',
            },
          },
        },
      },
    },

    editLink: {
      pattern: 'https://github.com/phil616/dst-server-icp/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页',
    },

    outline: { level: [2, 3], label: '本页导航' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    lastUpdatedText: '最后更新于',
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '菜单',
    darkModeSwitchLabel: '外观',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',

    footer: {
      message: '基于 MIT 许可发布',
      copyright: 'Copyright © 2025-present phil616',
    },
  },
})
