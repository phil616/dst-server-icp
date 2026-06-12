---
layout: home

hero:
  name: DST Serverd
  text: 饥荒联机版服务器管理系统
  tagline: 单机 · 无 Docker · 进程直管 —— 统一管理多个服务器分片与实例,重启后端不打断玩家
  image:
    src: /logo.png
    alt: DST Serverd
  actions:
    - theme: brand
      text: 快速开始
      link: /guide
    - theme: alt
      text: 技术架构
      link: /architecture
    - theme: alt
      text: GitHub
      link: https://github.com/phil616/dst-server-icp

features:
  - icon: 🧩
    title: 实例与配置管理
    details: 实例 CRUD、自动渲染 ini/lua、分配 LAN 端口;房间 / 密码 / 模式 / 人数 / PVP / tick_rate / Token 等结构化编辑。
  - icon: ⚙️
    title: 进程直管
    details: subprocess + setsid 启动 Shard,FIFO 注入命令,崩溃自动重启;后端重启凭 PID + FIFO + 日志 offset 重新接管已有 Shard,玩家不掉线。
  - icon: 🧱
    title: MOD 管理
    details: 增删启停、Steam Workshop API 更新检测、SteamCMD 下载,绕开游戏内损坏下载器。
  - icon: 💾
    title: 备份体系
    details: 游戏内快照回滚 + 文件级备份(手动 / 定时 / 还原前自动)+ 滚动清理 + 安全还原。
  - icon: 📦
    title: 安装与导入
    details: 一键 SteamCMD / 服务端本体(343050)/ MOD 安装,支持代理叠加;上传压缩包导入存档并重分配端口。
  - icon: 📡
    title: 实时可观测
    details: 活动流 + Shard 日志经 WebSocket 实时推送;前端 React + TypeScript + Ant Design 单页控制台。
---

## 这是什么

**dst-server-icp** 是饥荒联机版(Don't Starve Together)专用服务器的管理后端。

**单机、无 Docker** —— Python 后端用 `subprocess` 直接托管每个 Shard 进程,重启后凭 **PID + FIFO + 日志 offset** 重新接管已有 Shard,**不打断玩家**。后端由 uv + systemd 托管,前端为 React + TypeScript + Ant Design 单页应用,后端在 `/` 托管其构建产物。

> 默认部署在内网,不做认证 / 鉴权。详见[技术架构](/architecture)。

## 一键安装

安装:

```bash
curl -fsSL https://cnb.cool/greenshadecapital/dst-server-icp/-/git/raw/main/install-dst.sh | sudo bash -s -- install
```

升级:

```bash
curl -fsSL https://cnb.cool/greenshadecapital/dst-server-icp/-/git/raw/main/install-dst.sh | sudo bash -s -- update
```

## 文档导航

| 文档 | 说明 |
|---|---|
| [使用指南](/guide) | 安装配置、Web 控制台、实例 / MOD / 备份管理、API 参考、生产部署、故障排除 |
| [技术架构](/architecture) | DST 领域知识、进程直管架构、数据模型与落地约束 |
| [手动部署](/dst-server-setup) | Ubuntu / Debian 手动部署 DST 专用服务器(无面板,纯手动流程) |
| [打包与发布](/release) | 后端 tar.gz + GUI exe 的打包发布流程 |
