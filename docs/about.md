# 关于本项目

## 项目简介

**dst-server-icp**（Don't Starve Together Server Integrated Control Plane）是饥荒联机版（Don't Starve Together）专用服务器的管理后端。

本项目是一个**单机、无 Docker** 的轻量级服务器管理系统。Python 后端通过 `subprocess` 直接托管每个 Shard 进程，重启后凭 **PID + FIFO + 日志 offset** 重新接管已有 Shard，**不打断玩家**。前端为 React + TypeScript + Ant Design 单页应用，由后端在 `/` 托管其构建产物。

该项目不是传统意义上的前后端分离项目，由于阻塞模型的限制，前端页面通过FastAPI的staticfiles机制挂载，属于后端的一部分，但API仍可用

> 项目初始名称为`dst-serverd`，在源码和文档中`dst-serverd`和`dst-server-icp`可能混用，由于二者的字面量被多个子模块依赖，因此暂无统一修改的计划。

## 核心特性

| 特性 | 说明 |
|------|------|
| **实例管理** | 实例 CRUD、自动渲染 ini/lua、分配 LAN 端口 |
| **配置管理** | 房间/密码/模式/人数/PVP/tick_rate/Token 等结构化编辑 |
| **进程直管** | subprocess + setsid 启动 Shard，FIFO 注入命令，崩溃自动重启 |
| **MOD 管理** | 增删启停、Steam Workshop API 更新检测、SteamCMD 下载 |
| **备份体系** | 游戏内快照回滚 + 文件级备份（手动/定时/还原前自动）+ 滚动清理 |
| **安装与导入** | 一键 SteamCMD / 服务端本体 / MOD 安装，支持代理导入存档 |
| **实时可观测** | 活动流 + Shard 日志经 WebSocket 实时推送 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12+、FastAPI、Uvicorn、SQLite、psutil |
| 前端 | React、TypeScript、Ant Design、Vite |
| 进程管理 | Systemd（托管后端）、subprocess（托管 Shard） |
| 部署 | uv（包管理）、tar.gz 发布包、一键安装脚本 |

## 项目结构

```
src/dst_serverd/          # Python 后端
├── main.py               # FastAPI 入口
├── api/                  # 路由（health/instances/admin/ws）
├── services/             # 业务逻辑（编排/安装/备份）
├── supervisor/           # 进程监管（spec/fifo/pidfile/monitor/manager）
├── config.py / db.py     # 配置 + SQLite
├── render.py / ports.py  # ini/lua 渲染 + 端口分配
└── static/               # 前端构建产物
frontend/                 # React + TS + Ant Design（Vite）源码
docs/                     # VitePress 文档站
deploy/                   # systemd unit
scripts/                  # 测试辅助脚本
```

## 架构概览

### 进程模型

后端就是控制面，与 DST 本体同机共置，用 `subprocess` 直接把每个 Shard 当子进程拉起并全程托管：

- **启动**：`subprocess.Popen` 启动 Shard 进程
- **命令通道**：FIFO（命名管道）注入 `c_*` 命令
- **日志采集**：重定向 stdout/stderr 到文件，持续 tail 解析
- **存活监控**：PID 文件 + psutil 校验

### 后端部署

```
systemd  ──管理──▶  后端（Python，唯一权威）  ──管理──▶  各 Shard 游戏进程
```

systemd 只托管后端一个 unit（`KillMode=process`），后端管理所有 Shard 进程。重启后端时 Shard 进程保持运行，后端启动后重新接管。

## 仓库地址

- **GitHub**：<https://github.com/phil616/dst-server-icp>
- **CNB**：<https://cnb.cool/greenshadecapital/dst-server-icp>

关于双仓库：Github仓库旨在利用Github Action来更新文档站点，而CNB是国内仓库，可以在大陆地区加速下载uv和发布包等内容，速度更快，可以避免网络问题。