# DST Serverd 使用指南

## 目录

1. [快速开始](#1-快速开始)
2. [配置详解](#2-配置详解)
3. [Web 控制台](#3-web-控制台)
4. [实例管理](#4-实例管理)
5. [配置管理](#5-配置管理)
6. [MOD 管理](#6-mod-管理)
7. [备份与恢复](#7-备份与恢复)
8. [访问控制](#8-访问控制)
9. [导入外部存档](#9-导入外部存档)
10. [安装与更新](#10-安装与更新)
11. [代理设置](#11-代理设置)
12. [API 参考](#12-api-参考)
13. [冒烟测试](#13-冒烟测试)
14. [生产部署](#14-生产部署)
15. [故障排除](#15-故障排除)

---

## 1. 快速开始

### 1.1 前置要求

- **Python 3.12+** + [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- **Node.js 20+** + npm（仅开发前端时需要）
- **Linux x86_64**（DST 服务端只提供 amd64 构建）
- **Klei 账号及 Token**（在线服需要，[获取 Token](https://accounts.klei.com/account/game/subscriptions)）

### 1.2 安装与初始化

```bash
# 克隆仓库
git clone <repo-url> dst-serverd
cd dst-serverd

# 安装 Python 依赖
uv sync

# 构建前端
./make-web.sh

# 配置
cp config.yaml.example config.yaml
vim config.yaml   # 按需修改 base / port 等
```

### 1.3 启动

```bash
# 开发模式
uv run uvicorn dst_serverd.main:app --port 8000 --reload

# 浏览器打开 http://127.0.0.1:8000/
```

首次启动会自动创建必要的目录结构（`logs/`、`run/`、`clusters/` 等），并对账（reconcile）已配置的 Shard 进程。

### 1.4 验证

```bash
# 健康检查
curl http://127.0.0.1:8000/api/health
# → {"status":"ok"}

# 查看整体状态
curl http://127.0.0.1:8000/api/shards
```

---

## 2. 配置详解

### 2.1 config.yaml

配置文件查找顺序（优先级从高到低）：
1. `$DSTD_CONFIG` 环境变量指向的文件
2. 当前工作目录下的 `config.yaml`
3. 仓库根目录下的 `config.yaml`
4. `/etc/dst-serverd/config.yaml`

```yaml
# DST 安装根目录
base: /opt/dst

# Cluster 配置目录名: <base>/<conf_dir>/<cluster>/
conf_dir: clusters

# 后端监听地址
host: 127.0.0.1
port: 8000

# SQLite 数据库路径（相对 config.yaml 所在目录）
db: data/dstd.sqlite3

# 密钥（当前版本未用于鉴权，保留供将来使用）
secret_key: change-me

# 优雅关停超时（秒）
shutdown_grace: 30
sigterm_grace: 10
```

**路径布局**（以 `base=/opt/dst` 为例）：

```
/opt/dst/
├── server/                   # DST 服务端程序（SteamCMD app_update 343050）
│   └── bin64/
│       └── dontstarve_dedicated_server_nullrenderer_x64
├── steamcmd/                 # SteamCMD 工具
├── clusters/                 # Cluster 实例目录
│   ├── Cluster_1/
│   │   ├── cluster.ini
│   │   ├── Master/
│   │   └── Caves/
│   └── Cluster_2/
├── ugc_mods/                 # MOD UGCHandler 目录
├── logs/                     # 后端活动日志 + Shard 游戏日志
├── run/                      # PID 文件 / FIFO / Spec / offset
└── mods/                     # 依赖注入的 MOD（可选）
```

### 2.2 运行时配置

部分配置存储在 SQLite 数据库的 `kv` 表中，可通过 Web 控制台或 API 修改：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `backup_auto_enabled` | `0` | 是否启用自动备份 |
| `backup_interval_min` | `360` | 自动备份间隔（分钟） |
| `backup_retention` | `10` | 每个实例保留备份份数 |

---

## 3. Web 控制台

前端为 React + TypeScript + Ant Design 单页应用，由后端在 `/` 托管。执行 `./make-web.sh` 构建后访问 `http://<host>:<port>/` 即可。

### 3.1 导航

左侧侧边栏包含 4 个主要模块：

| 菜单 | 路径 | 功能 |
|------|------|------|
| 总览 | `/` | 统计卡片 + 所有 Shard 实时状态表 |
| 实例 | `/instances` | 实例列表 CRUD，点击进入详情 |
| 安装 | `/install` | SteamCMD/服务端/MOD 安装与更新 |
| 代理 | `/proxy` | 下载代理设置 |

右侧上方按钮可打开**活动抽屉**，实时显示后端操作日志（WebSocket 推送）。

### 3.2 主题

全局使用 antd 暗色主题（`algorithm: dark`），中文语言包（`zhCN`）。

---

## 4. 实例管理

一个"实例"（Instance）对应 DST 的一个 Cluster（集群），包含一个 Master Shard（地上）和可选的一个 Caves Shard（洞穴）。

### 4.1 创建实例

1. 进入 **实例 → 创建实例**
2. 填写：
   - **名称** — 实例显示名，自动生成 Cluster_ 目录名
   - **游戏模式** — `生存` / `荒野` / `无尽`
   - **游戏风格** — `休闲` / `默认` / `疯狂` / `放松`
   - **最大玩家数**
   - **启用洞穴** — 是否创建 Caves Shard
   - **在线模式** — 启用需填写 Klei Token
3. 确认后自动：
   - 分配互不冲突的端口（server_port / master_server_port / auth_port）
   - 渲染 `cluster.ini` / `server.ini` / `worldgenoverride.lua` / `modoverrides.lua`
   - 写入数据库

或用 API：

```bash
curl -X POST http://127.0.0.1:8000/api/instances \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "My DST Server",
    "mode": "endless",
    "intention": "cooperative",
    "max_players": 6,
    "caves": true,
    "online": true,
    "token": "pds-g^KU_xxx..."
  }'
```

### 4.2 启动/停止/重启

在实例列表点击对应按钮，或在详情页操作。

```bash
# 启动
curl -X POST http://127.0.0.1:8000/api/instances/{id}/start

# 停止（先 c_shutdown 优雅停服，再 SIGTERM 兜底）
curl -X POST http://127.0.0.1:8000/api/instances/{id}/stop

# 重启
curl -X POST http://127.0.0.1:8000/api/instances/{id}/restart
```

### 4.3 发送控制台命令

```bash
curl -X POST http://127.0.0.1:8000/api/instances/{id}/shards/{shard}/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "c_rollback(2)"}'
```

### 4.4 删除实例

删除实例会停止其所有进程并清理目录与数据库记录。

> **注意**：删除前建议先创建备份。

### 4.5 后端重启不中断游戏

这是本项目的关键特性。后端 `KillMode=process`，重启时：
- **只杀 Python 进程**，Shard 游戏进程不受影响（已通过 `setsid` 脱离）
- 后端重启后，通过 `run/` 目录下的 PID 文件 + FIFO + 日志 offset，**重新接管**已有进程
- 玩家无感知，游戏不中断

---

## 5. 配置管理

### 5.1 结构化编辑

实例详情 → **配置** 选项卡，可编辑：

- **Cluster 配置**：房间名、描述、密码、模式、风格、人数、PVP、tick_rate、投票、自动保存、快照数、whitelist_slots、仅局域网、在线/Token
- **Shard 配置**：各 Shard 独立设置

修改会自动写回 `cluster.ini` / `server.ini`，并支持解析落盘配置进行核对。

### 5.2 原始配置查看

`GET /api/instances/{id}/config/raw` 返回磁盘上实际的配置内容，可用于调试。

---

## 6. MOD 管理

### 6.1 添加 MOD

实例详情 → **MOD** 选项卡：
1. 输入 Workshop ID（Steam 创意工坊 MOD 的数字 ID）
2. 配置 MOD 选项（可选）
3. 确认后自动渲染 `modoverrides.lua` 和 `dedicated_server_mods_setup.lua`

### 6.2 更新检测

系统通过 **Steam Web API**（`ISteamRemoteStorage/GetPublishedFileDetails`）批量查询已安装 MOD 的最后更新时间，与本地基线比对，标记出 `outdated` 的 MOD。

```bash
# 触发更新检测
curl -X POST http://127.0.0.1:8000/api/instances/{id}/mods/check-updates
```

### 6.3 MOD 更新

使用 **SteamCMD** (`workshop_download_item 322330 <id>`) 下载 MOD，绕开游戏内损坏的下载器（解决 `ODPF failed` / `library folder not found` 等问题）。

```bash
# 更新单个 MOD
curl -X POST http://127.0.0.1:8000/api/instances/{id}/mods/{workshop_id}/update

# 更新全部 MOD（后台作业）
curl -X POST http://127.0.0.1:8000/api/instances/{id}/mods/update
```

### 6.4 MOD 加载确认

系统解析服务器日志中的 `Loading mod:` 行，确认 MOD 真正载入游戏并显示版本号，而非仅下载完成。

### 6.5 修复 Steam 库

```bash
curl -X POST http://127.0.0.1:8000/api/install/repair-library
```

这会重新复制 `steamclient.so` 到服务端的 lib 目录，修复游戏内下载器。

---

## 7. 备份与恢复

### 7.1 手动备份

实例详情 → **备份** 选项卡 → 点击**创建备份**。

```bash
curl -X POST http://127.0.0.1:8000/api/instances/{id}/backups
```

### 7.2 自动备份

在实例详情 → **备份** 选项卡中配置自动备份策略：

| 配置 | 说明 |
|------|------|
| 启用/停用 | 自动备份总开关 |
| 间隔（分钟） | 多久创建一次备份（默认 360 分钟） |
| 保留份数 | 最多保留多少份（默认 10 份，超出自动删除最旧的） |

自动备份在后台异步执行，只备份**正在运行**的实例。

### 7.3 备份列表与操作

```bash
# 列出备份
curl http://127.0.0.1:8000/api/instances/{id}/backups

# 恢复备份（自动停服 → 预备份 → 覆盖 → 可选重启）
curl -X POST http://127.0.0.1:8000/api/backups/{backup_id}/restore

# 下载备份
curl -O http://127.0.0.1:8000/api/backups/{backup_id}/download

# 删除备份
curl -X DELETE http://127.0.0.1:8000/api/backups/{backup_id}
```

### 7.4 游戏内快照回滚

通过控制台命令实现：

```bash
# 在 Web 控制台 Console 中输入
c_rollback(2)   # 回滚到 2 个快照前

# 或用 API
curl -X POST http://127.0.0.1:8000/api/instances/{id}/shards/{shard}/rollback \
  -H 'Content-Type: application/json' \
  -d '{"snapshots": 2}'
```

### 7.5 还原前自动备份

系统在执行还原操作前自动创建一份备份，确保可回退。

---

## 8. 访问控制

### 8.1 概念

DST 使用 Klei ID（`KU_xxx` / `OU_xxx`）标识玩家。访问控制即管理三个 `.txt` 文件：

| 文件 | 说明 |
|------|------|
| `adminlist.txt` | 管理员（可执行游戏内管理命令） |
| `whitelist.txt` | 白名单（仅白名单玩家可加入） |
| `blocklist.txt` | 黑名单（禁止加入） |

### 8.2 管理

实例详情 → **访问控制** 选项卡，分为三列：
- 添加：输入 Klei ID 并指定类型
- 删除：点击条目旁的删除按钮

```bash
# 添加管理员
curl -X POST http://127.0.0.1:8000/api/instances/{id}/access \
  -H 'Content-Type: application/json' \
  -d '{"kind": "admin", "klei_id": "KU_xxxxxxx"}'

# 移除
curl -X DELETE http://127.0.0.1:8000/api/instances/{id}/access/admin/KU_xxxxxxx
```

---

## 9. 导入外部存档

支持导入已有 DST 服务器的存档（`.tar.gz` / `.zip`），保留世界数据。

### 9.1 导入流程

1. 导出存档：将目标服务器的 `Cluster_xxx/` 目录打包
2. 在 Web 控制台 → **实例** → **导入实例**
3. 上传压缩包，可选的覆盖名称/Token
4. 系统自动：
   - 解析 `cluster.ini` / `server.ini` / `worldgenoverride.lua` / `modoverrides.lua`
   - 读取访问列表（adminlist/whitelist/blocklist）
   - 解析端口，冲突则重新分配
   - **保留**：存档数据（`save/` 目录）、`[ACCOUNT]` 字段、MOD 配置选项
   - 启动后直接从已有存档续世界，**不重新生成**

### 9.2 API

```bash
curl -X POST http://127.0.0.1:8000/api/instances/import \
  -F 'file=@Cluster_Archive.tar.gz' \
  -F 'name=My Imported Server' \
  -F 'token=pds-g^KU_xxx...'
```

---

## 10. 安装与更新

### 10.1 SteamCMD

```bash
# 安装/更新 SteamCMD
curl -X POST http://127.0.0.1:8000/api/install/steamcmd

# 或 Web 控制台 → 安装 → 安装 SteamCMD
```

### 10.2 DST 服务端

```bash
# 安装/更新 DST 服务端（SteamCMD app_update 343050）
curl -X POST http://127.0.0.1:8000/api/install/server
```

### 10.3 全部 MOD 更新

```bash
# 更新所有已安装的 Workshop MOD
curl -X POST http://127.0.0.1:8000/api/install/mods
```

### 10.4 后台作业

安装/更新任务在后台异步执行，可通过 API 查询进度：

```bash
# 查看所有作业
curl http://127.0.0.1:8000/api/jobs

# 查看某个作业详情
curl http://127.0.0.1:8000/api/jobs/{job_id}
```

Web 控制台在 **安装** 页面展示实时作业日志。

---

## 11. 代理设置

对于需要代理才能访问 Steam 网络的环境（如中国大陆 VPS），系统提供灵活的代理配置。

### 11.1 模式

| 模式 | 说明 |
|------|------|
| `off` | 不使用代理 |
| `env` | 通过环境变量注入 `http_proxy`/`https_proxy`/`no_proxy`（仅作用于安装/下载子进程，不影响 Shard） |
| `force` | 使用 `proxychains4` 强制代理 |

### 11.2 配置

```bash
# 查看当前代理配置
curl http://127.0.0.1:8000/api/proxy

# 设置代理
curl -X PUT http://127.0.0.1:8000/api/proxy \
  -H 'Content-Type: application/json' \
  -d '{
    "enabled": true,
    "mode": "env",
    "scheme": "http",
    "host": "127.0.0.1",
    "port": 7890,
    "no_proxy": "127.0.0.1,localhost"
  }'
```

> **重要**：代理配置**只影响** SteamCMD / MOD 下载等安装更新操作，**绝不注入**到游戏 Shard 进程的环境变量中，确保游戏运行不受干扰。

---

## 12. API 参考

### 12.1 核心

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/shards` | 所有 Shard 实时状态 |

### 12.2 实例

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/instances` | 实例列表 |
| POST | `/api/instances` | 创建实例 |
| POST | `/api/instances/import` | 导入存档 |
| GET | `/api/instances/{id}` | 实例详情 |
| DELETE | `/api/instances/{id}` | 删除实例 |
| PATCH | `/api/instances/{id}` | 更新配置 |
| POST | `/api/instances/{id}/start` | 启动 |
| POST | `/api/instances/{id}/stop` | 停止 |
| POST | `/api/instances/{id}/restart` | 重启 |
| POST | `/api/instances/{id}/shards/{s}/command` | 控制台命令 |
| POST | `/api/instances/{id}/shards/{s}/rollback` | 回滚快照 |
| GET | `/api/instances/{id}/config/raw` | 原始配置 |
| GET | `/api/instances/{id}/saves` | 存档信息 |

### 12.3 MOD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/instances/{id}/mods` | 添加 MOD |
| PATCH | `/api/instances/{id}/mods/{w}` | 更新 MOD |
| DELETE | `/api/instances/{id}/mods/{w}` | 移除 MOD |
| POST | `/api/instances/{id}/mods/check-updates` | 检测更新 |
| POST | `/api/instances/{id}/mods/update` | 全部更新 |
| POST | `/api/instances/{id}/mods/{w}/update` | 单个更新 |

### 12.4 备份

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/instances/{id}/backups` | 创建备份 |
| GET | `/api/instances/{id}/backups` | 备份列表 |
| POST | `/api/backups/{id}/restore` | 恢复 |
| DELETE | `/api/backups/{id}` | 删除 |
| GET | `/api/backups/{id}/download` | 下载 |

### 12.5 访问控制

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/instances/{id}/access` | 列表 |
| POST | `/api/instances/{id}/access` | 添加 |
| DELETE | `/api/instances/{id}/access/{kind}/{kid}` | 移除 |

### 12.6 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/proxy` | 代理配置 |
| PUT | `/api/proxy` | 保存代理 |
| POST | `/api/install/steamcmd` | 安装 SteamCMD |
| POST | `/api/install/server` | 更新服务端 |
| POST | `/api/install/mods` | 更新全部 MOD |
| POST | `/api/install/repair-library` | 修复 Steam 库 |
| GET | `/api/jobs` | 作业列表 |
| GET | `/api/jobs/{id}` | 作业详情 |
| GET | `/api/activity` | 活动日志 |
| GET | `/api/settings/backup` | 备份策略 |
| PUT | `/api/settings/backup` | 保存备份策略 |

### 12.7 WebSocket

| 类型 | 路径 | 说明 |
|------|------|------|
| WS | `/api/instances/{c}/shards/{s}/logs/ws` | Shard 游戏日志实时推送 |
| WS | `/api/activity/ws` | 全局活动流实时推送 |

---

## 13. 生产部署

### 13.1 systemd 托管

```bash
# 1) 构建前端
./make-web.sh

# 2) 安装依赖（仅生产）
uv sync --frozen --no-dev

# 3) 写配置
cp config.yaml.example config.yaml
vim config.yaml   # 配置 base / port

# 4) 安装 systemd 单元
sudo cp deploy/dst-serverd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dst-serverd
```

### 13.2 systemd 单元要点

```ini
[Service]
User=dst
Group=dst
WorkingDirectory=/opt/dst-serverd
ExecStartPre=/usr/local/bin/uv sync --frozen --no-dev
ExecStart=/opt/dst-serverd/.venv/bin/uvicorn dst_serverd.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
KillMode=process       # 关键：只杀 Python，不杀 Shard 子进程
TimeoutStopSec=20
LimitNOFILE=65536
```

- **`KillMode=process`** — 重启后端时游戏进程保持运行，后端重连即可
- **直接调用 `.venv/bin/uvicorn`** — 确保 systemd 主 PID 即 Python 进程
- **`Restart=always`** — 崩溃自动恢复

### 13.3 日志查看

```bash
# 后端日志
journalctl -u dst-serverd -f

# 游戏日志
# /opt/dst/logs/<Cluster>__<Shard>/game.log

# 活动日志
# /opt/dst/logs/activity.log
```

---

## 14. 故障排除

### 14.1 前端显示"尚未构建"

执行 `./make-web.sh` 构建前端，然后刷新页面。

### 14.2 后端启动失败

```bash
# 检查 config.yaml 是否存在
ls -l config.yaml

# 手动运行查看错误
uv run uvicorn dst_serverd.main:app --port 8000

# 检查端口占用
ss -tlnp | grep 8000
```

### 14.3 Shard 进程不启动

```bash
# 查看具体 Shard 日志
# /opt/dst/logs/<Cluster>__<Shard>/game.log

# 检查服务端是否已安装
/opt/dst/server/bin64/dontstarve_dedicated_server_nullrenderer_x64 --version

# 检查 Token 是否有效（在线模式）
cat /opt/dst/clusters/<Cluster>/cluster_token.txt
```

### 14.4 MOD 下载失败

1. 检查网络连接（尤其是中国大陆 VPS）
2. 配置代理：Web 控制台 → **代理** → 设置 HTTP/SOCKS5 代理
3. 尝试修复 Steam 库：
   ```bash
   curl -X POST http://127.0.0.1:8000/api/install/repair-library
   ```

### 14.5 端口冲突

创建实例时端口自动分配，如果手动修改可能会冲突。检查端口占用：

```bash
ss -tlnp | grep -E '1099[0-9]|1101[0-8]|2701[0-9]|876[6-8]|1088[0-9]|1089[0-8]'
```

### 14.6 后端重启后 Shard 未接管

检查 `run/` 目录下的 PID 文件和 Spec 文件：

```bash
ls -l /opt/dst/run/
cat /opt/dst/run/<Cluster>__<Shard>.pid
```

若 PID 文件丢失或进程已死，手动启动即可。

---

> 更多技术细节请参见 [architecture.md](architecture.md)。
> 手动 DST 服务端部署流程请参见 [dst-server-setup.md](dst-server-setup.md)。
