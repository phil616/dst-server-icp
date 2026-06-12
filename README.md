<div align="center">
  <img src="./docs/images/logo-nbg.png" alt="Dst-serverd Logo" width="100">
  <h1>dst-server-icp</h1>
  <p>饥荒联机版服务器管理系统,统一管理多个服务器分片和实例</p>

  [文档](https://dst-serverd-wiki.dreamreflex.com/) · [一键安装](#一键安装)
</div>

饥荒联机版(Don't Starve Together)专用服务器管理后端。

单机、**无 Docker**，Python 后端用 `subprocess` 直接托管每个 Shard 进程，重启后凭 PID + FIFO + 日志 offset 重新接管已有 Shard，**不打断玩家**。后端由 uv + systemd 托管，前端为 React + TypeScript + Ant Design 单页应用，后端在 `/` 托管其构建产物。

> 部署在内网，不做认证/鉴权。详见 [docs/architecture.md](./docs/architecture.md)。

## 快速开始

```bash
uv sync                          # 安装依赖
cp config.yaml.example config.yaml  # 编辑 base/db/port
./make-web.sh                    # 构建前端
uv run uvicorn dst_serverd.main:app --port 8000
```
打开 `http://127.0.0.1:8000/` 即可。

## 一键安装
1. 安装
```
curl -fsSL https://cnb.cool/greenshadecapital/dst-server-icp/-/git/raw/main/install-dst.sh | sudo bash -s -- install
```

2. 升级
```
curl -fsSL https://cnb.cool/greenshadecapital/dst-server-icp/-/git/raw/main/install-dst.sh | sudo bash -s -- update
```
## 功能一览

- **实例 CRUD** — 自动渲染 ini/lua、分配 LAN 端口
- **配置管理** — 房间/密码/模式/人数/PVP/tick_rate/Token 等结构化编辑
- **访问控制** — 管理员/白名单/黑名单
- **进程托管** — subprocess + setsid 启动 Shard，FIFO 注入命令，崩溃自动重启，后端重启游戏不掉线
- **MOD 管理** — 增删启停、更新检测(Steam Workshop API)、SteamCMD 下载(绕开游戏内损坏下载器)
- **安装/更新** — SteamCMD、服务端本体(343050)、MOD，支持代理叠加
- **备份体系** — 游戏内快照回滚 + 文件级备份(手动/定时/还原前自动)+ 滚动清理 + 安全还原
- **导入存档** — 上传压缩包，解析配置、重分配端口、保留存档
- **可观测** — 活动流 + Shard 日志经 WebSocket 实时推送

## 生产部署

```bash
./make-web.sh
uv sync --frozen --no-dev
cp config.yaml.example config.yaml
sudo cp deploy/dst-serverd.service /etc/systemd/system/
sudo systemctl enable --now dst-serverd
```

关键: `KillMode=process`(重启后端不杀游戏), `Restart=always`。

## 目录结构

```
src/dst_serverd/          # Python 后端
├── main.py               # FastAPI 入口
├── api/                  # 路由(health/instances/admin/ws)
├── services/             # 业务逻辑(编排/安装/备份)
├── supervisor/           # 进程监管(spec/fifo/pidfile/monitor/manager)
├── config.py / db.py     # 配置 + SQLite
├── render.py / ports.py  # ini/lua 渲染 + 端口分配
└── static/               # 前端构建产物
frontend/                 # React + TS + Ant Design(Vite)源码
docs/                     # 文档
scripts/                  # 测试辅助脚本
deploy/                   # systemd unit
```

## 文档

| 文档 | 说明 |
|---|---|
| [docs/guide.md](docs/guide.md) | 使用指南（安装/配置/运维/API/故障排除） |
| [docs/architecture.md](docs/architecture.md) | 技术方案（领域知识 + 进程直管架构 + 数据模型） |
| [docs/dst-server-setup.md](docs/dst-server-setup.md) | DST 服务器手动部署指南 |
