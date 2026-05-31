# dst-serverd

饥荒联机版(Don't Starve Together)专用服务器管理后端。

**架构(详见 [docs/architecture.md](./docs/architecture.md)):** 单机、**无 Docker**。Python 后端是唯一管理权威,用
`subprocess` 直接托管每个 Shard 游戏进程 —— 命令走 FIFO、日志走文件、存活/资源用 psutil 监控;
后端自身由 **uv + systemd** 托管,重启后凭 PID 文件 + FIFO + 日志 offset **重新接管**已运行的
Shard,不打断玩家。

> **部署在内网,不做认证/鉴权**(见 docs/architecture.md 2.8)。前端为 **React + TypeScript + Ant Design**
> 单页应用,后端在 `/` 托管其构建产物。

## 功能

- **实例(Cluster)CRUD**:创建即渲染 cluster.ini / server.ini / worldgenoverride.lua /
  modoverrides.lua,自动分配互不冲突端口(server_port 落在 LAN 可见区间)。
- **配置管理**:房间名/描述/密码、模式/风格、人数/PVP、tick_rate、投票、自动保存、快照数、
  whitelist_slots、仅局域网、在线/Token 等结构化编辑(写回 ini),并能**解析回**落盘配置核对。
- **访问控制**:管理员 / 白名单 / 黑名单(KU_/OU_)管理,渲染 adminlist/whitelist/blocklist.txt。
- **进程托管**:`subprocess + setsid` 启动 Shard,FIFO 注入命令,日志文件 + psutil 监控,
  崩溃自动重启;**后端重启凭 PID/FIFO/offset 重新接管,游戏不掉线**。
- **MOD 管理**:增删 / 启停 / 看配置;**更新检测**(Steam Workshop API 比对 time_updated)+ 一键更新;
  **加载确认**(解析服务器日志 `Loading mod` 行,确认 MOD 真正载入游戏并显示版本,而非仅下载完成);
  **下载机制用 SteamCMD `workshop_download_item 322330 <id>` → `mods/workshop-<id>/`**(绕开游戏内损坏的
  下载器,解决 `ODPF failed` / `library folder not found`)+ 覆盖 steamclient.so + 子进程超时(防卡死);
  支持单 MOD/全部更新,失败如实上报。
- **安装/更新**:SteamCMD、服务端本体(343050)、Workshop MOD,后台作业 + **叠加代理**(env / proxychains)。
- **存档与备份体系**:游戏内快照回滚(`c_rollback`)+ 文件级备份(手动/定时/还原前自动)+
  保留份数滚动清理 + 安全还原(停服→预备份→覆盖→可选重启)+ 下载 + 存档自省。
- **导入外界存档**:上传一个 Cluster 压缩包(.tar.gz/.zip),解析配置、重新分配端口并**保留存档**,
  启动即续原世界(不重新生成)。
- **可观测**:统一活动流(后台编排事件 + Shard 状态流转 + 安装输出)+ 每 Shard 游戏日志,均
  经 WebSocket 实时推送,前端可复制。
- **前端**:运行总览 / 实例管理 / MOD 管理 / 备份 / 安装更新 / 代理设置 分模块,Ant Design 企业级组件。

## 文档

| 文档 | 说明 |
|---|---|
| [docs/guide.md](docs/guide.md) | 使用指南（安装/配置/运维/API/故障排除） |
| [docs/architecture.md](docs/architecture.md) | 技术方案（领域知识 + 进程直管架构 + 数据模型） |
| [docs/dst-server-setup.md](docs/dst-server-setup.md) | DST 服务器手动部署指南 |

## 目录结构

```
src/dst_serverd/
├── config.py            # 环境变量配置(DST_BASE 等)+ 路径布局
├── db.py / models.py    # SQLite 持久化 + 领域模型
├── render.py / ports.py # ini/lua 渲染 + 端口分配
├── proxy.py             # 下载代理(env / proxychains)
├── main.py              # FastAPI 入口;lifespan 做 reconcile + 监管循环
├── api/                 # core(health/shards)/ instances / admin(install,proxy)/ ws
├── services/            # instances(编排)/ install / backups
├── supervisor/          # 进程监管核心(spec/fifo/pidfile/monitor/logtail/process/manager)
├── activity.py / jobs.py # 活动流(可观测)+ 后台作业
└── static/              # 前端构建产物(由 make-web.sh 生成,后端用 StaticFiles 托管)
frontend/                # React + TS + Ant Design(Vite)源码
├── src/api/             # axios 端点 + React Query hooks + 类型
├── src/components/      # 布局 / 活动抽屉 / 日志查看器 / 状态标签
└── src/modules/         # dashboard / instances / mods / backups / install / proxy(分模块)
docs/                    # 文档(架构 / 部署指南)
config.yaml.example      # 配置模板(复制为 config.yaml)
make-web.sh              # 构建前端并整合到 static/(单项目启动)
deploy/                  # systemd unit
scripts/                 # fake_dst / fake_steamcmd + smoke_*
docs/                    # 文档(使用指南 + 架构 + 部署指南)
```

## 配置(config.yaml)

不用环境变量;复制 `config.yaml.example` 为 `config.yaml`,填 `base`(DST 安装根)、`db`、`host`/`port` 等。
查找顺序:`$DSTD_CONFIG` → `./config.yaml` → 仓库根 → `/etc/dst-serverd/config.yaml`。

## 开发与验证

```bash
uv sync
./make-web.sh          # 构建前端 → src/dst_serverd/static/(单项目,后端直接托管,无需 dev 服务器)
cp config.yaml.example config.yaml   # 按需改 base / db / port

# 冒烟测试(伪 DST,无需真实游戏)
uv run python scripts/smoke_test.py    # 进程托管:启动/就绪/注入/重新接管/优雅停服
uv run python scripts/smoke_full.py    # 全栈:建实例+渲染/端口/MOD/备份/安装(代理)/启停删
uv run python scripts/smoke_config.py  # 配置更新/访问控制/解析/存档自省/备份保留与删除
uv run python scripts/smoke_import.py  # 导入外界存档:解析/重分配端口/保留存档/续世界启动
uv run python scripts/smoke_modupdate.py  # MOD 更新检测状态机 + 日志解析"已加载到游戏"
uv run python scripts/smoke_repair.py     # MOD 下载(SteamCMD)+ steamclient 修复 + 超时

# 单项目启动(后端同时托管前端),打开 http://127.0.0.1:8000/ 即为控制台
uv run uvicorn dst_serverd.main:app --port 8000
```

> 前端改源码时也可用 dev 热更:`cd frontend && npm run dev`(:5173,代理 /api 到 :8000);
> 改完跑 `./make-web.sh` 同步到 static/ 即可。

主要接口:`GET /api/instances`、`POST /api/instances`(建)、`POST /api/instances/{id}/{start|stop|restart}`、
`POST /api/instances/{id}/shards/{shard}/command`、`POST /api/instances/{id}/mods`、
`POST /api/instances/{id}/backups`、`POST /api/install/{steamcmd|server|mods}`、`GET /api/jobs`、
`GET|PUT /api/proxy`、`WS /api/activity/ws`、`WS /api/instances/{cluster}/shards/{shard}/logs/ws`。

## 生产部署(uv + systemd,单项目)

见 [docs/architecture.md §2.10](./docs/architecture.md)。要点:`KillMode=process`(重启后端不杀游戏)、运行时用
`.venv` 解释器(使 systemd 主 PID 即 Python)、`Restart=always`。前端构建产物整合进 `static/`,
后端单进程同时托管 API 与前端,无需 dev 服务器。

```bash
# 1) 构建并整合前端到 static/
./make-web.sh
# 2) 安装后端依赖
uv sync --frozen --no-dev
# 3) 写配置
cp config.yaml.example config.yaml   # 编辑 base / db / port
# 4) 安装 systemd 单元(config.yaml 放在 WorkingDirectory=/opt/dst-serverd 下即被自动读取)
sudo cp deploy/dst-serverd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dst-serverd
```
