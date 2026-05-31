# 饥荒联机版(DST)服务器管理中心 — 技术方案

> 本文档面向实现。第一部分(领域知识)是后续所有技术决策的事实依据,**必须先读懂**;第二部分(技术方案)给出针对 DST 运转机制做的**进程直管 / 控制面**设计(**单机、无 Docker**,Python 后端用 `subprocess` 直接托管 Shard 进程);第三部分给出落地约束与数据模型。所有 DST 行为均以 Klei 官方文档与官方 Wiki 为准。

---

## 第一部分:DST 专用服务器领域知识(事实依据)

### 1.1 服务器程序本质

- DST 专用服务器是游戏本体中只保留游戏逻辑、剥离全部图形渲染的组件,可执行文件为 `dontstarve_dedicated_server_nullrenderer`(32 位)与 `dontstarve_dedicated_server_nullrenderer_x64`(64 位,推荐)。
- 程序通过 **SteamCMD** 安装,Steam AppID 为 **343050**(专用服务器工具)。安装命令:
  ```
  login anonymous
  force_install_dir /path/to/install
  app_update 343050 validate
  ```
  `validate` 会做完整性校验并删除不属于游戏的文件——**安装了手动 MOD 时更新要省略 `validate`**,否则手动 MOD 会被清掉。
- 官方只提供 **Windows / Linux 的 x86 与 x86_64** 构建,**不支持 ARM/非 x86**。这直接限定了宿主机架构必须是 `amd64`。
- 服务器程序本身无需拥有游戏即可安装;但**运行在线服务器需要拥有 DST + 一个 Klei 账号**(用于生成 cluster token)。离线服务器不需要。一份 DST 拷贝可托管任意数量在线服务器实例。
- 客户端与服务器走同一套网络层,**NAT 穿透与中继由 Klei 自动处理**(客户端无法直连时自动走中继)。

### 1.2 核心模型:Cluster(集群) 与 Shard(分片)

这是整个系统最重要的概念,面板的"一个服务器实例"必须映射到 DST 的 **一个 Cluster**:

- 一个 DST 服务器实例 = **一个 Cluster**,Cluster 由 **若干 Shard** 组成。
- 每个 Shard 是 **一个独立的服务器进程**,运行一个具体世界。
- 一个 Cluster 有且仅有 **一个 Master Shard**,外加 **任意数量的 Secondary Shard**。
- 约定:Master Shard 跑地上世界(Forest / Overworld),一个 Secondary Shard 跑洞穴(Caves)。原版即"地上 + 洞穴"两个 Shard。带洞穴的服务器 = **2 个进程**。
- Shard 之间通过 **UDP** 互联:Master 在 `master_port` 监听,Secondary 用 `master_ip:master_port` 连接 Master,并用 `cluster_key` 做认证。玩家在地上和洞穴之间穿梭 = 在两个 Shard 进程之间迁移角色数据。

> **关键设计含义**:面板里"创建一个服务器"= 创建一个 Cluster = 至少要拉起 1 个(纯地上)或 2 个(地上+洞穴)Shard 进程。本方案**不使用 Docker**:**后端用 Python `subprocess` 直接托管每个 Shard 进程**,同一 Cluster 的多个 Shard 共享同一份 Cluster 配置/存档目录。

### 1.3 目录结构

默认持久化根目录:Linux `~/.klei/DoNotStarveTogether`,Windows `%USERPROFILE%/Documents/Klei`。完整路径由启动参数拼成:
`<persistent_storage_root>/<conf_dir>/<cluster>/<shard>/`

一个 Cluster 的标准目录:
```
<cluster>/                       # 例如 Cluster_1
├── cluster.ini                  # 整个 Cluster 共享的配置(必需)
├── cluster_token.txt            # Klei 在线认证令牌(仅在线服需要)
├── adminlist.txt                # 管理员 KU_ ID 列表(可选,每行一个)
├── whitelist.txt                # 白名单(可选)
├── blocklist.txt                # 黑名单(可选)
├── Master/                      # 地上 Shard 目录
│   ├── server.ini               # 该 Shard 的配置(必需)
│   ├── worldgenoverride.lua     # 世界生成设置(人类可读,推荐用它)
│   ├── leveldataoverride.lua    # 世界设置(内部格式,二者并存时覆盖前者)
│   ├── modoverrides.lua         # 该 Shard 启用/配置哪些 MOD(可选)
│   └── save/                    # 存档 + 快照 (session/<sessionid>/)
└── Caves/                       # 洞穴 Shard 目录(文件同 Master)
    └── ...
```

MOD 安装目录是 **安装级别的全局目录**,不在 Cluster 目录里(见 1.6)。

### 1.4 cluster.ini(Cluster 级配置,所有 Shard 共享)

分为五个 section。标"主 only"的项只在 Master 所在机器的 cluster.ini 生效;标"须各机一致"的项在多机部署时每份 cluster.ini 必须相同。

**[MISC]**
- `max_snapshots`:默认 6。保留的快照数量,每次保存生成一个,对应游戏内"回滚"标签可回滚的份数。
- `console_enabled`:默认 true。允许在服务器进程的标准输入/终端执行 Lua 命令。**Agent 注入管理命令依赖此项必须为 true。**

**[SHARD]**
- `shard_enabled`:默认 false。多 Shard 必须 true(须各机一致)。
- `bind_ip`:默认 127.0.0.1。Master 监听其它 Shard 连接的地址。同机全部 Shard → 127.0.0.1;跨机 → 0.0.0.0。仅 Master 需要(可写在 server.ini 覆盖)。
- `master_ip`:Secondary 连接 Master 用的 IP,同机为 127.0.0.1。`is_master=false` 时必需。
- `master_port`:默认 10888,UDP。Master 监听、Secondary 连接用的 Shard 间通信端口。同机所有 Shard 应一致;且必须与任何同机 Shard 的 `server_port` 不同。
- `cluster_key`:Shard 认证口令。`shard_enabled=true` 时必需(须各机一致)。

**[STEAM]**
- `steam_group_only` / `steam_group_id` / `steam_group_admins`:Steam 群组限制与群组管理员。

**[NETWORK]**
- `offline_cluster`:默认 false。true = 离线集群(不公开列出、仅局域网、无 Steam 功能)。**是否在线只由该项决定;在线集群必须有 cluster_token.txt 否则拒绝启动,离线集群即使有 token 也忽略。**(须各机一致)
- `tick_rate`:默认 15。每秒服务器→客户端更新次数,建议保持 15。
- `whitelist_slots`:默认 0,白名单预留槽位数(主 only)。**应与 whitelist.txt 条目数一致**;若槽位多于条目会异常(官方 Wiki),且存在"仅最后一条 ID 生效"的已知 bug;槽位从 `max_players` 中预留(预留 N 个则公开位 = max_players − N)。
- `cluster_password`:加入密码,空=无密码(主 only)。
- `cluster_name`:服务器列表显示名(主 only)。
- `cluster_description`:描述(主 only)。
- `lan_only_cluster`:默认 false,仅局域网(主 only)。
- `cluster_intention`:玩法风格,取值 `cooperative` / `competitive` / `social` / `madness`(主 only)。
- `autosaver_enabled`:默认 true。false = 不再每天结束自动保存(关服仍保存,可用 `c_save()` 手动保存)。

**[GAMEPLAY]**
- `max_players`:默认 16,最大同时在线人数(主 only)。
- `pvp`:默认 false。
- `game_mode`:默认 survival,取值 `survival` / `endless` / `wilderness`(须各机一致)。
- `pause_when_empty`:默认 false。无人时暂停(强烈建议 true 以省 CPU)。
- `vote_enabled`:默认 true,投票功能开关。

### 1.5 server.ini(每个 Shard 各一份)

**[SHARD]**
- `is_master`:`shard_enabled=true` 时必需。每个 Cluster 恰有一个 Shard 为 true,其余 false。
- `name`:Shard 名(写日志用),Secondary 且 `shard_enabled=true` 时必需;Master 始终显示为 `[SHDMASTER]`。
- `id`:Shard 唯一数字 ID,Secondary 自动生成。**不要随意改/删,否则正处于该世界的玩家角色可能出问题。**

**[STEAM]**(同机多 Shard 必须互不相同)
- `authentication_port`:默认 8766。
- `master_server_port`:默认 27016。

**[NETWORK]**
- `server_port`:默认 10999,UDP,玩家连接端口。同机多 Shard 必须不同;**须在 10998–11018 之间才能被局域网列表看到**;<1024 在部分系统需要特权。

### 1.6 MOD 加载机制(实现 MOD 管理的核心)

MOD 是 **两阶段**:**安装(install,安装级全局)** + **启用与配置(enable+configure,每 Shard)**。

**(A) 安装**
- 推荐方式:在安装目录的 `mods/dedicated_server_mods_setup.lua` 里声明,每行一个:
  ```lua
  ServerModSetup("378160973")   -- Global Position
  ServerModSetup("375859599")   -- Health Info
  ```
  也支持整个 Workshop 合集。服务器进程启动时会**自动下载并更新**该文件列出的所有 MOD(除非加 `-skip_update_server_mods`)。仅当 Workshop 上版本变化时才更新,因此正常开服很快。
- 手动安装(非 Workshop 的 MOD):在安装目录 `mods/` 下建一个目录放入 MOD 文件,目录名即"MOD 名",可任意取。每个 MOD 至少包含 `modinfo.lua` 与 `modmain.lua`。

**(B) V1 与 V2(UGC)MOD 的安装位置差异**
- V1 MOD:装在 `mods/workshop-<WorkshopID>`。
- V2(UGC)MOD:默认装在 `<SERVER_DIR>/ugc_mods/<cluster>/<shard>/`——**每个 Shard 各下载一份,极浪费磁盘并拖慢启动**。可用 `-ugc_directory <path>` 改到统一目录。
- 两者对外**都用 `workshop-<WorkshopID>` 这个名字引用**,所以 modoverrides 里写法一致,无需区分 V1/V2。

**(C) 启用与配置:每个 Shard 的 modoverrides.lua**
- 返回一个 Lua table,key 为 MOD 名,value 含 `enabled` 与可选 `configuration_options`:
  ```lua
  return {
    ["workshop-378160973"] = { enabled = true },
    ["workshop-375859599"] = {
      enabled = true,
      configuration_options = {
        show_type = 0,
        divider   = 5,
        use_blacklist = true,
      },
    },
  }
  ```
- 安装是全局的,但 **启用与配置是每 Shard 的**。绝大多数情况下,同一 Cluster 的所有 Shard 应启用**相同的 MOD 集合与相同配置**,否则会不兼容。
- 通过该文件可把配置写成 GUI 里没有的非法值,可能导致 MOD 异常,谨慎。

**(D) MOD 配置项的元信息来源:modinfo.lua**
- 每个 MOD 目录里的 `modinfo.lua` 含 `configuration_options`,定义了该 MOD 可配置项,结构如下(面板可解析它来渲染配置表单):
  ```lua
  configuration_options = {
    {
      name = "item_durability",          -- 写入 modoverrides 用的 key
      label = "Item Durability",         -- 给人看的名字
      options = {
        { description = "Low",    data = 50  },
        { description = "Normal", data = 100 },
        { description = "High",   data = 150 },
      },
      default = 100,                      -- 默认值
    },
  }
  ```
  同时 `modinfo.lua` 还含 `name`、`description`、`version`、`api_version`、`all_clients_require_mod`、`client_only_mod`、`dst_compatible`、`icon`/`icon_atlas` 等元信息。
- **要让面板展示/编辑某 MOD 的可配置项,需读取该 MOD 目录下 modinfo.lua 的 `configuration_options`**;要修改生效则写入对应 Shard 的 modoverrides.lua。

**(E) MOD 更新的推荐工作流(更新最佳实践)**
- 不要让每个 Shard 启动时各自更新 MOD(会产生竞态、重复下载)。改为:
  1. 先跑一个**临时 updater 进程**,加 `-only_update_server_mods`(只更新 MOD 然后退出),并用 `-ugc_directory` 指向**共享的 MOD 目录**;
  2. 各 Shard 再以 `-skip_update_server_mods` 启动,并指向同一 `-ugc_directory`。
- 这样 MOD 只下载一份、所有 Shard 共用,启动快且无竞态。

### 1.7 网络与端口(端口规划与防火墙依据)

| 端口 | 协议 | 默认 | 配置位置 / 参数 | 作用 | 约束 |
|---|---|---|---|---|---|
| 玩家连接 | UDP | 10999 | `server.ini [NETWORK] server_port` / `-port` | 客户端连入 | 同机各 Shard 必须不同;10998–11018 才能被 LAN 列表看到 |
| Shard 间通信 | UDP | 10888 | `cluster.ini [SHARD] master_port` | Master↔Secondary | 同机各 Shard 一致;须 ≠ 同机任何 server_port |
| Steam master | UDP | 27016 | `server.ini [STEAM] master_server_port` / `-steam_master_server_port` | Steam 内部 | 同机各 Shard 必须不同 |
| Steam auth | UDP | 8766 | `server.ini [STEAM] authentication_port` / `-steam_authentication_port` | Steam 内部 | 同机各 Shard 必须不同 |

全部为 **UDP**。对外只需开放各 Shard 的 `server_port`;`master_port` 仅 Shard 间使用;Steam 两个端口为内部用途。

### 1.8 启动参数(进程编排依据)

可执行文件**要求工作目录为其 `bin/` 目录**。典型启动(分别拉起两个 Shard):
```
dontstarve_dedicated_server_nullrenderer_x64 -console \
  -persistent_storage_root <root> -conf_dir <conf> \
  -cluster <cluster> -shard Master
# 第二条把 -shard 换成 Caves
```
关键参数:
- `-persistent_storage_root <abs>`:持久化根(绝对路径)。
- `-conf_dir <name>`:配置目录名(无斜杠),默认 `DoNotStarveTogether`。
- `-cluster <name>`:Cluster 目录名,默认 `Cluster_1`。
- `-shard <name>`:Shard 目录名,默认 `Master`。
- `-port` / `-players` / `-tick` / `-bind_ip`:覆盖对应 ini 项。
- `-steam_master_server_port` / `-steam_authentication_port`:同机多 Shard 必须不同。
- `-ugc_directory <path>`:V2 MOD 安装目录(用于多 Shard 共享)。
- `-console`:开启标准输入命令通道(Agent 注入命令依赖)。
- `-offline`:强制离线+LAN(等价 `offline_cluster=true` 且 `lan_only_cluster=true`)。
- `-disabledatacollection`:禁用数据采集(将只能离线)。
- `-skip_update_server_mods`:启动时跳过 MOD 更新。
- `-only_update_server_mods`:只更新 MOD 然后退出(配合 updater 进程)。

### 1.9 存档 / 快照 / 备份 / 回滚机制

- 存档位于每个 Shard 的 `save/`,内部以 `session/<sessionid>/` 组织。**存档只在服务器侧**。
- 自动保存时机:**每天开始**(便于崩溃恢复与回滚)+ **关服时**;可 `c_save()` 手动保存;`autosaver_enabled=false` 可关掉每日自动保存。
- 每次保存生成一个**快照(snapshot)**,保留份数由 `cluster.ini [MISC] max_snapshots`(默认 6)控制,对应游戏内"回滚"可回退的份数。
- **回滚** = 还原到先前快照:`c_rollback()` 回退 1 份,`c_rollback(3)` 回退 3 份,`c_rollback(0)` 等价重置当前。
- **完整文件级备份/还原**:直接拷贝/打包整个 Cluster 目录(配置 + save)即可;还原即把目录覆盖回去。面板可在文件层面做"备份整 Cluster 目录"。

### 1.10 管理控制台命令(Agent 下发动作的指令集)

需要 `console_enabled=true` 且以 admin 身份;命令喂给服务器进程标准输入即可执行:
- `c_save()`:强制保存。
- `c_shutdown(true|false)`:关服,true 保存后退出(`c_shutdown()` 默认 true),false 不保存退出。
- `c_rollback(n)`:回滚 n 个快照。
- `c_regenerateworld()`:**永久删除并重生整个 Cluster 的所有世界**(危险)。
- `c_regenerateshard()`:仅重生当前 Shard(可保留设置)。
- `c_announce("msg")`:服务器公告(关服/重启前提醒玩家)。
- `c_listplayers()`:列出在线玩家。
- `TheNet:Kick(userid)`:踢人。
- `TheNet:SetAllowIncomingConnections(true|false)`:开/关新连接。
- `c_stopvote()`:停止当前投票。

### 1.11 性能特性(资源规划依据)

- 每个 Shard 是**单进程、对单核 CPU 敏感**;一个带洞穴的服务器是两个进程。
- 内存经验值:6 人小服每 Shard 约 700MB–1GB 起,人多与大量 MOD 显著上升;建议宿主机有富余内存。
- `pause_when_empty=true` 在无人时暂停可显著省 CPU。
- 玩家上限超过约 6–8 人时延迟与稳定性风险上升,与 MOD 数量、tick_rate 相关。

---

## 第二部分:针对 DST 机制的技术方案

### 2.0 概念映射(贯穿全系统)

```
面板"服务器实例(ServerInstance)"  ⟷  一个 DST Cluster
一个 Cluster                       ⟷  1 个 cluster.ini + N 个 Shard
一个 Shard                         ⟷  1 个由后端 subprocess 直接托管的游戏进程 + 1 份 server.ini
同一 Cluster 的所有 Shard           ⟷  共享同一份磁盘目录(配置 + 存档)+ 共享同一份安装级 MOD 目录
```

### 2.1 进程模型:Python 后端直接托管 Shard 进程(无 Docker)

后端就是控制面,与 DST 本体同机共置,**用 `subprocess` 直接把每个 Shard 当子进程拉起并全程托管**:

- **启动**:`subprocess.Popen` 起 `dontstarve_dedicated_server_nullrenderer_x64`,**工作目录(cwd)必须设为安装目录的 `bin64/`**(游戏强制要求 cwd 为其 bin 目录)。一个带洞穴的实例 = 后端管理 **2 个子进程**(Master + Caves);纯地上 = 1 个。同机可并存多个 Cluster 的多个子进程,靠端口分配隔离。
- **命令通道用 FIFO(命名管道)而非裸 `Popen.stdin`**:为每个 Shard 建一个 FIFO,启动时把游戏 stdin 重定向自该 FIFO,后端持其写端注入 `c_*` 命令。好处:进程生命周期与后端解耦——**后端重启后重新打开同一 FIFO 即可继续注入命令,无需重启游戏**(裸 `Popen.stdin` 在后端退出时即失效)。
- **日志采集**:游戏 stdout/stderr 重定向到 `<base>/logs/<cluster>_<shard>.log`;后端起一个 tail 任务持续读取、解析事件,并记录 offset(后端重启后从上次位置续读)。
- **存活与资源**:写 PID 文件,用 `psutil`(按 PID 校验 cmdline)判存活、采 CPU/内存;`/proc/<pid>` 失踪即视为崩溃,按策略自动重启。
- **可重新接管**:Shard 用 `setsid` 脱离后端会话独立运行;后端自身由 **uv + systemd** 托管、开机自启,重启后凭 **PID 文件 + FIFO + 日志 offset 重新接管**已在运行的 Shard,不打断玩家(部署与 `KillMode=process` 见 2.10)。
- **不再用 screen / Docker**:手工方案用 screen 只为"后台 + 可交互",这里用 FIFO + 日志文件 + psutil 完整替代且可程序化;不引入容器与镜像。

### 2.2 磁盘目录布局(宿主机文件系统,无卷)

单一安装根 `<base>`(如 `/opt/dst` 或 steam 用户家目录),全部为普通目录:
```
<base>/
├── steamcmd/                       # SteamCMD 自身
├── server/                         # DST 服务端本体(AppID 343050),含 bin64/
│   └── mods/                       # 安装级 V1 MOD + dedicated_server_mods_setup.lua + modsettings.lua
├── ugc_mods/                       # 安装级 V2/UGC MOD 统一目录(-ugc_directory 指向此)
├── logs/                           # 各 Shard 控制台日志 + FIFO
└── clusters/
    └── <cluster>/                  # 一个实例 = 一个 Cluster 目录
        ├── cluster.ini
        ├── cluster_token.txt       # 在线服必需(由用户填写)
        ├── adminlist.txt / whitelist.txt / blocklist.txt
        ├── Master/  { server.ini, worldgenoverride.lua, modoverrides.lua, save/ }
        └── Caves/   { server.ini, worldgenoverride.lua, modoverrides.lua, save/ }
```
说明:
- 启动用 `-persistent_storage_root <base>` + `-conf_dir`(目录名,如 `clusters`)+ `-cluster <cluster>`/`-shard <shard>` 定位到具体 Shard 目录。
- **MOD 安装是安装级全局**:`server/mods` 与 `ugc_mods` 由本机所有 Cluster 共享一份;`dedicated_server_mods_setup.lua` 列"全机要下载哪些 MOD"(并集),各 Shard 的 `modoverrides.lua` 控制"本 Shard 启用/配置哪些"。不同 Cluster 要不同 MOD 集合,靠 modoverrides 启用差异实现,无需多份安装。
- 游戏本体只装一份(约 2GB),多 Cluster 共用同一 `server/`;`dedicated_server_mods_setup.lua`、`modsettings.lua` 由后端预置在 `server/mods` 下。
- 备份 = 直接打包 `clusters/<cluster>/` 整个目录。

### 2.3 实例生命周期编排

**创建实例(Cluster)**:
1. 面板生成 `cluster.ini`(填入 cluster_name/password/game_mode/max_players/pvp/max_snapshots 等)写入 `clusters/<cluster>/`;在线服写入用户提供的 `cluster_token.txt`。
2. 为每个 Shard 生成 `server.ini`(分配互不冲突的 server_port / steam 两端口)、`worldgenoverride.lua`(Master 用地上 preset,如 `SURVIVAL_TOGETHER`;Caves 用 `DST_CAVE`)、空/初始 `modoverrides.lua`。
3. 写 `adminlist.txt`(实例所有者的 KU_ ID)。

**启动**:
1. (按需)跑一次性 **MOD updater 子进程**:`<dst_bin> -only_update_server_mods -ugc_directory <base>/ugc_mods …`,`Popen` 起、`wait()` 完即退出(可叠加代理,见 2.9)。
2. 为 Master 建 FIFO 与日志文件,`Popen` 起 Master 子进程(cwd=`server/bin64`,stdin←FIFO,stdout/stderr→log;参数 `-console -skip_update_server_mods -ugc_directory <ugc> -persistent_storage_root <base> -conf_dir <conf> -cluster <cluster> -shard Master`),tail 日志等 `Sim paused`。
3. 同法起 Caves 子进程(`-shard Caves`,端口另分配),等日志"与 Master 互联成功"。
4. 顺序:Master 先于 Secondary;Secondary 会主动连 `master_ip:master_port`。写 PID 文件,标记 instance=running。

**优雅关闭 / 重启**(避免玩家被硬断、避免存档损坏):
1. 先 `c_announce("...")` 预告。
2. 向该 Shard 的 FIFO 写 `c_shutdown(true)` 让进程**保存后自行退出**。
3. `poll()` 等待进程退出;超时 `SIGTERM` → 再超时 `SIGKILL` 兜底;清理 FIFO 与句柄。
- 因后端是子进程的管理者且命令走 FIFO,无需 Docker exec、`/proc/1/fd/0` 或去 TTY 等容器手法。

### 2.4 配置变更(改 ini / lua 元信息)

- 面板对 `cluster.ini` / `server.ini` 采用**结构化字段编辑**(按 1.4/1.5 的 section→key 建模),序列化为 ini 文本写回 `clusters/<cluster>/`;对 `worldgenoverride.lua` / `modoverrides.lua` 采用**Lua table 模板渲染**写回。
- **绝大多数配置变更需要重启对应 Shard 才生效**(世界生成类只在重新生成世界时生效)。少量运行期可调项可通过控制台命令热改(如 `TheNet:SetAllowIncomingConnections`)。
- 写回前做校验:端口冲突检查(同机/同 Cluster 的 server_port、Steam 端口互斥)、`is_master` 唯一性、`shard_enabled/cluster_key/game_mode` 跨 Shard 一致性、在线服必须有 token。
- `id` 字段(server.ini)生成后**禁止面板擅改**。

### 2.5 MOD 管理

- **添加 MOD**:面板把 Workshop ID 追加进 `dedicated_server_mods_setup.lua`(`server/mods` 安装目录),并在每个 Shard 的 `modoverrides.lua` 加 `["workshop-<id>"]={enabled=true,...}`。
- **更新 MOD**:跑 updater 子进程(`-only_update_server_mods`)即可,无需改任何配置;之后重启 Shard 加载新版本。MOD 仅在 Workshop 版本变化时才真正下载。
- **配置 MOD**:MOD 下载后解析其目录 `modinfo.lua` 的 `configuration_options`(name/label/options[].{description,data}/default)渲染表单;用户选择后写入对应 Shard `modoverrides.lua` 的 `configuration_options`。
- **删除/停用**:从 `dedicated_server_mods_setup.lua` 移除(或保留安装但在 modoverrides 置 `enabled=false`);重启生效。
- **多 Shard 一致性**:默认对同 Cluster 所有 Shard 写入相同 MOD 集合与配置。
- **非 Workshop MOD**:支持上传到 `server/mods` 下的命名目录(目录名即 MOD 名),在 modoverrides 用该目录名引用。

**已实现的 MOD 更新检测与加载确认**(`services/modupdate.py` + `supervisor/logtail.py`):
- **更新检测**:经 Steam Web API `ISteamRemoteStorage/GetPublishedFileDetails`(公开、免 key)批量查每个
  Workshop MOD 的 `time_updated`,与 DB 基线 `installed_time_updated` 比较 → `latest`/`outdated`/`unknown`。
  基线在**每次成功更新后对齐**(`mark_all_installed_current`);可叠加 2.9 代理。
- **下载机制(已重构,关键)**:**不再用游戏内置的 `-only_update_server_mods`** —— 它依赖游戏自带
  `steamclient.so`,在很多 Linux 部署上报 `ODPF failed entirely: 16` / `Staging/Install library folder
  not found` 而下载失败(经 Klei 论坛与开源镜像 docker-dst-server 等证实是 steamclient.so 损坏)。
  改为用 **SteamCMD `+login anonymous +workshop_download_item 322330 <id>`(游戏 AppID 322330,非 343050)**
  逐个下载,再拷进 **`server/mods/workshop-<id>/`(V1 路径)**;Shard 以 `-skip_update_server_mods` 启动即加载。
  此路径用 SteamCMD 自带(可用)的 steamclient,**彻底绕开损坏的游戏内下载器**。已用真实 SteamCMD 拉取真实
  MOD 验证通过。
- **双保险 + 健壮性**:下载前把 **SteamCMD 的 `steamclient.so` 覆盖到 `server/bin64/lib64` 与 `bin/lib32`**
  (`fix_steamclient`,修游戏内下载器);所有下载子进程**带超时 + killpg**(`_run(timeout=…)`),避免卡死
  阻塞作业队列(此前 `run_lock` 串行 + 无超时会导致一个卡死作业拖垮后续全部"排队中")。
- **更新动作**:`更新全部`(下载 DB 内全部 workshop MOD)/ `更新该 MOD`(SteamCMD 单物品下载,真正的
  单 MOD 更新);失败带原因(`error_hint`)经活动流 + `/api/jobs` 上报,前端弹成功/失败。
  另有手动 `POST /api/install/repair-library`(校验安装 + 覆盖 steamclient.so)兜底。
- **加载确认(不止下载完成)**:解析服务器日志的 `Loading mod: workshop-<id> (Name) Version:X.Y`
  行,得到该 MOD **是否真正载入运行中的游戏** + 名称 + 已加载版本(按 Shard 区分);`Disabling/failed`
  视为加载失败。后端重启后会补扫日志恢复该状态。

### 2.6 备份与回滚

提供两层能力,分别对应 DST 的两种机制:
1. **游戏内快照回滚**(轻量、快):面板调用 `c_rollback(n)`,n 受 `max_snapshots` 限制;适合"刚被破坏想退回几个存档点"。
2. **文件级备份/还原**(完整、可跨时间):打包整个 Cluster 目录(配置 + save),存到备份存储;还原即停服→覆盖目录→启服。建议备份前先 `c_save()` 确保落盘。
- 备份策略建议:定时(cron)+ 手动 + 关键操作(MOD 更新/世界重生前)自动各打一份;保留 N 份滚动清理。

**已实现的备份体系**(对应代码 `services/backups.py` + `services/scheduler.py` + `services/save.py`):
- **触发类型(trigger)**:`manual`(手动)/ `auto`(定时调度)/ `pre-restore`(还原前自动)/ `pre-update`(危险操作前)。
- **滚动清理**:每次备份后按 `backup_retention`(kv 设置)保留最近 N 份,旧的连文件带 DB 记录一并删除。
- **自动调度**:后台 asyncio 循环(`BackupScheduler`)按 `backup_interval_min` 对**运行中**实例打 `auto` 备份;由 `backup_auto_enabled` 开关。
- **安全还原**:`停服 → pre-restore 预备份 → tar 覆盖回 clusters/<cluster>/ → 可选重启`,避免覆盖时进程占用与不可逆。
- **存档自省**:读 `<Shard>/save/session/<id>/` 报告会话数、文件数、占用大小(`save.py`),前端展示并提供 `c_rollback(n)` 入口。
- **下载**:`GET /api/backups/{id}/download` 直接下载 tar.gz。
- **导入外界存档**(`services/importer.py`,`POST /api/instances/import`):上传一个 Cluster
  压缩包(.tar.gz/.tgz/.tar/.zip,含 cluster.ini + Master/Caves 及其 save/)→ 解析
  cluster.ini/server.ini/列表,用 **Lua 解析器(`lua.py`)** 解析 modoverrides.lua(含
  `configuration_options`,支持中文/空串键)→ 入库 → 落到 clusters/<新名>/。
  端口**优先沿用存档原值**(`resolve_port`,保住防火墙/端口转发),仅冲突才另分配;落地时
  **只就地改端口**(`set_ini_value`),保留 `[ACCOUNT] encode_user_path`、Secondary `id`、
  `cluster_language`/`cloud_id`、modoverrides、save/ 等全部原字段。因 DST 在存档存在时加载已有
  世界、不重新生成,启动即**续上传入的世界**。解压用 `tarfile(filter='data')` / `zipfile` 防越权。

### 2.7 后端进程监管模块职责(原 Agent 职责,现内置于后端)

单机共置后无需独立 Agent / gRPC;以下职责由后端的一个监管模块直接完成(每个 Shard 子进程对应一组「FIFO 写端 + 日志 tail 任务 + PID 监控」):

- **进程管理与健康**:`Popen` 拉起/监管 Shard 子进程,PID 文件 + `psutil` 判存活、采 CPU/内存,崩溃按策略自动重启。
- **日志采集**:tail 各 Shard 日志文件,解析关键事件(Shard 注册、Shard 互联成功、玩家加入/退出含 KU_ ID、MOD 加载、崩溃栈)。
- **命令下发通道**:向该 Shard 的 FIFO 写入 1.10 的控制台命令;结果从日志解析(如 `c_listplayers()` 输出)。
- **与前端连接**:后端内部事件总线 → **WebSocket/SSE** 把状态/日志实时推给 React。
- **就绪判定**:Master 看到 `Sim paused` 视为就绪;Secondary 还需在日志确认与 Master 互联成功。

### 2.8 控制面与技术栈映射(单机、无 Docker)

- **后端 Python/FastAPI**:实例/Shard/MOD/备份的 CRUD 与编排;SQLite 持久化元数据;**直接用 `subprocess` + `psutil` 管理 Shard 进程(不经 Docker)**;进程监管循环、日志解析、命令注入(FIFO)均在后端进程内;经 WebSocket/SSE 向前端推日志与状态。后端自身用 **uv + systemd** 托管、开机自启(部署与生命周期见 2.10)。
- **前端 React**:实例总览、Shard 状态、配置表单(由 cluster.ini/server.ini 字段模型驱动)、MOD 管理(由 modinfo.lua 配置项驱动)、日志/控制台、备份与回滚操作台。
- **无独立 Agent、无 gRPC、无容器**;SteamCMD/服务端本体/MOD 的安装与更新由后端拉起子进程完成(可叠加代理,见 2.9)。

### 2.9 网络代理方案(SteamCMD / 服务端本体 / MOD 下载更新加速)

**要解决的问题**:三类**出站下载**在受限/不稳定网络下易慢易失败,面板需提供一个**可配置代理**,让用户填一个代理地址后,这些下载走代理而非宿主机直连:

- (a) 下载 **SteamCMD 自身**(`steamcmd_linux.tar.gz`,curl/wget,HTTPS);
- (b) 下载/更新 **DST 服务端本体**(SteamCMD `app_update 343050`:Steam CM 握手 + CDN 内容下载,均为 HTTP/HTTPS over **TCP**);
- (c) 下载/更新 **Workshop MOD**(updater 子进程 `-only_update_server_mods`,内部同样走 SteamCMD/Steam);
- (可选 d) **面板后端自身出站**(调 Steam Web API / Workshop 拉 MOD 名称与 `configuration_options` 渲染表单)。

**硬边界——绝不走代理的流量**:运行态 Shard 的**游戏流量**(玩家连接、Klei NAT/中继、Shard 间 UDP 通信)**一律直连**。这些是 **UDP** 且必须对外可达,经代理会破坏连接与 NAT 穿透。由于运行态 Shard 一律以 `-skip_update_server_mods` 启动、自身不下载任何东西,天然不需要代理;**代理只作用于"下载/更新"动作所在的子进程**(后端用 `Popen(env=…)` 拉起的那几个),与运行态 Shard 子进程在编排上完全分离。

**代理配置模型(面板可编辑,持久化到 SQLite)**:

| 字段 | 取值 / 说明 |
|---|---|
| `enabled` | 是否启用代理 |
| `mode` | `off` / `env`(环境变量,默认) / `force`(强制路由,proxychains 兜底) |
| `scheme` | `http` / `https` / `socks5` |
| `host` / `port` | 代理地址,如 `http://127.0.0.1:7890` 拆分存储 |
| `username` / `password` | 可选,带认证的代理;UI 掩码、日志脱敏、入库加密 |
| `no_proxy` | 直连白名单,默认含 `127.0.0.1,localhost,<内网/Shard IP 段>` |
| 作用域 | 全局单例(单机) |

**实现分两层(默认第一层,失败再升第二层)**:

**第一层 `env`(默认,覆盖绝大多数场景)**——向"执行下载的子进程"注入 `http_proxy` / `https_proxy` / `all_proxy` / `no_proxy`(及大写同名变量):

- SteamCMD tarball 的 curl/wget 直接遵循 `http(s)_proxy`,或等价用 `curl -x <proxy>`;
- SteamCMD 的 Steam CM 握手(现代走 443 上的 WebSocket)与 CDN 内容下载(HTTP)在多数环境下遵循 `http(s)_proxy`;
- **后端子进程注入**:`subprocess.Popen(cmd, env={**os.environ, "http_proxy":…, "https_proxy":…, "no_proxy":…})` 拉起 SteamCMD 安装、`app_update 343050`、MOD updater 子进程;
- **运行态 Shard 子进程不注入**这些变量(其 `Popen(env=…)` 不含代理),从源头保证游戏流量直连。

**第二层 `force`(env 不生效时的兜底)**——用 `proxychains-ng` 在 libc `connect()` 层把 SteamCMD 的**全部 TCP 连接**强制导向代理(支持 `socks5`/`http`):

- 宿主机预装 `proxychains-ng`(命令 `proxychains4`);面板按代理配置渲染 `proxychains.conf`(见 3.2);
- 下载/更新命令包一层:`proxychains4 -f <conf> steamcmd.sh +login anonymous +app_update 343050 …`、`proxychains4 -f <conf> <dst_bin> -only_update_server_mods …`;
- proxychains 只代理 TCP——而所有下载都是 TCP,足够;它**只包裹下载/更新进程,绝不包裹运行态 Shard**(Shard 是 UDP,且不应被代理)。

**编排落点(把代理钩进既有流程)**:

1. **SteamCMD 安装 / 服务端本体下载子进程**:读代理配置 → 设 `Popen(env=…)`(或 `proxychains4` 包裹)→ 下载。
2. **MOD updater 子进程**(对应 2.3 启动序列第 1 步):注入 env;`mode=force` 时改用 `proxychains4` 包裹。
3. **游戏版本更新子进程**(临时跑 `app_update 343050`;装有手动 MOD 时省略 `validate`):同上。
4. **(可选)面板后端 HTTP 客户端**:读同一份代理配置,以 `proxies=` 调 Steam Web API。

**自检与回退**:保存代理配置时提供"连通性自检"(经代理 GET 一个已知 Steam/CDN URL,返回耗时与状态);`env` 模式拉取失败可一键切 `force` 重试;置 `off` 即恢复直连。代理仅影响下载速度与成败,不改变任何 DST 运行语义。

### 2.10 后端部署与生命周期(uv + systemd)

目标:让 **Python 后端成为唯一的管理权威**,systemd 只负责"让后端永远活着、开机自启、被意外打断后自动拉起",而 DST 的进程/配置/MOD/备份/端口全部归后端管。

**职责边界(谁管谁)**——`systemd` **只托管「后端」这一个 unit**,**不为任何 Shard 建 unit**(那会把权力分给 systemd):
```
systemd  ──管理──▶  后端(Python,唯一权威)  ──管理──▶  各 Shard 游戏进程(subprocess + FIFO + 日志)
```

**uv 的角色**:用 `uv` 管理项目、锁定依赖(`uv.lock`)与 Python 版本;部署期 `uv sync --frozen` 生成 `.venv`。**运行时直接用 `.venv` 内的解释器**(而非 `uv run` 包装),使 systemd 跟踪的主 PID 就是 Python 本身,便于精确的信号与生命周期控制。

**systemd unit(示例 `/etc/systemd/system/dst-serverd.service`)**:
```ini
[Unit]
Description=DST Serverd — DST 服务器管理后端
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
# 专用低权限用户,DST 安装树归其所有(仅安装系统依赖/写 unit 时才需 root)
User=dst
Group=dst
WorkingDirectory=/opt/dst-serverd
# 配置来自 WorkingDirectory 下的 config.yaml(不再用环境变量);前端已由 ./make-web.sh 整合进 static/
ExecStartPre=/usr/local/bin/uv sync --frozen --no-dev
# 直接用 venv 解释器,使 systemd 主 PID 就是 Python(而非 uv 包装层)
ExecStart=/opt/dst-serverd/.venv/bin/uvicorn dst_serverd.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
# 关键:重启/停止后端只杀 Python 主进程,不连带杀 Shard 游戏进程(见下)
KillMode=process
TimeoutStopSec=20
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```
配置写在 `/opt/dst-serverd/config.yaml`(由 `config.yaml.example` 复制,见 2.2 / config.py),
不用环境变量。前端构建产物由 `./make-web.sh` 整合进 `src/dst_serverd/static/`,后端用
`StaticFiles` 在 `/` 托管,与 API **同一进程**(单项目启动,无需前端 dev 服务器)。

**关键:`KillMode=process`(后端重启,游戏不掉线)**:systemd 默认 `KillMode=control-group`,**停止/重启 unit 时会杀掉该 unit cgroup 内的全部进程**——包括后端拉起的 Shard。设为 `process` 后,`systemctl restart` 只终止 Python 主进程,Shard 不受影响;再配合后端启动时**重新接管**(PID 文件 + FIFO + 日志 offset),即可"**更新/重启后端而玩家不掉线**"。Shard 由后端以 `setsid` 脱离会话启动,避免被 SIGHUP 连带终止。

**后端 SIGTERM 语义(被 systemd 停止时)**:收到停止信号 = **优雅分离**——落盘日志 offset、关闭各 FIFO 写端、持久化运行态后退出;**绝不主动关 Shard**。只有用户在面板上显式"停止实例"才走 `c_announce → c_shutdown(true)` 真正关服。

**开机/重启对账(reconciliation)**:后端启动时读取 `server_instances.desired_status`,对 `running` 的实例:Shard 仍在(PID 文件 + `/proc/<pid>` + cmdline 校验)则重新接管;已不在(如整机重启后)则按既定参数重新拉起。即"期望状态=running 就保持在跑"。

**可选 sd_notify 看门狗**(进一步防"卡死"):实现 sd_notify 后,把 `Type=exec` 改 `Type=notify`,加 `NotifyAccess=main` 与 `WatchdogSec=30`;后端启动完成发 `READY=1`、周期发 `WATCHDOG=1`,卡死超时 systemd 自动重启后端。

**常用命令**:
```
sudo systemctl daemon-reload
sudo systemctl enable --now dst-serverd     # 开机自启 + 立即启动
systemctl status dst-serverd
journalctl -u dst-serverd -f                # 后端日志(游戏日志仍在 <base>/logs/)
sudo systemctl restart dst-serverd          # 后端重启,游戏不掉线(KillMode=process)
```

---

## 第三部分:落地约束、校验规则与数据模型

### 3.1 硬约束清单(实现时必须满足)

1. 宿主机架构必须 `amd64`(官方无 ARM 构建)。
2. 在线 Cluster 必须有合法 `cluster_token.txt`,否则进程拒绝启动;`offline_cluster` 决定在线/离线。
3. 同一 Cluster 内 `is_master=true` 的 Shard 有且仅有一个。
4. 同机/同 Cluster 各 Shard 的 `server_port`、`master_server_port`、`authentication_port` 必须两两不冲突;`master_port` 须 ≠ 任一 `server_port`。
5. 玩家可见于 LAN 要求 `server_port` ∈ [10998, 11018]。
6. `shard_enabled` / `cluster_key` / `game_mode` 等"须各机一致"项跨 Shard 必须相同。
7. MOD 更新优先用 `-only_update_server_mods` updater,Shard 启动一律 `-skip_update_server_mods` 并共享 `-ugc_directory`。
8. 配置类变更默认需重启对应 Shard;世界生成项仅重生世界时生效。
9. 关服/重启走 `c_announce` → 向 FIFO 写 `c_shutdown(true)`(进程保存后自退)→ `poll()` 等待退出,超时 `SIGTERM`/`SIGKILL` 兜底。
10. 不擅自修改 server.ini 的 `id`;手动 MOD 存在时 SteamCMD 更新省略 `validate`。
11. 代理仅作用于**下载/更新**(SteamCMD 本体、服务端本体、MOD)所在子进程;运行态 Shard 游戏流量(玩家连接、Klei 中继、Shard 间 UDP)**一律直连,严禁经代理**。`no_proxy` 必含本机与 Shard 内网地址;`proxychains` 只可包裹下载/更新子进程。
12. Shard 进程的 cwd 必须为 `server/bin64`;后端以 `subprocess` 直接托管,命令走每 Shard 的 FIFO、日志走文件;后端自身由 systemd 托管、开机自启。
13. 后端须能凭 PID 文件 + FIFO + 日志 offset **重新接管**已运行的 Shard;Shard 用 `setsid` 脱离后端会话,避免后端退出连带杀子进程。
14. 后端 systemd unit 须 `KillMode=process`:默认 `control-group` 会在停止/重启后端时连带杀掉同 cgroup 的 Shard;设为 `process` 后重启后端只终止 Python 主进程,Shard 存活,后端启动时按期望状态(`server_instances.desired_status=running`)对账并重新接管/补起。systemd 只托管后端一个 unit,不为 Shard 建 unit。运行时用 `.venv` 解释器(非 `uv run`),使主 PID 即 Python。

### 3.2 配置序列化要点

- `cluster.ini` / `server.ini`:标准 INI,按 section 分组,布尔写 `true/false`,空值项可省略走默认。
- `worldgenoverride.lua`:`return { override_enabled=true, preset="<preset>", overrides={...} }`,地上常用 `SURVIVAL_TOGETHER`/`SURVIVAL_TOGETHER_CLASSIC`/`SURVIVAL_DEFAULT_PLUS`/`COMPLETE_DARKNESS`,洞穴用 `DST_CAVE`。
- `modoverrides.lua`:`return { ["workshop-<id>"] = { enabled=<bool>, configuration_options={ <key>=<value>, ... } }, ... }`。
- `dedicated_server_mods_setup.lua`:逐行 `ServerModSetup("<id>")`。
- `proxychains.conf`(仅 `mode=force` 时渲染):末尾 `[ProxyList]` 段写一行,`socks5 <host> <port> [<user> <pass>]` 或 `http <host> <port> [<user> <pass>]`;头部设 `strict_chain`、`proxy_dns`(socks5 时建议开,避免 DNS 走本机)。

### 3.3 建议的持久化数据模型(SQLite,字段示意)

- `server_instances`:id、name、cluster_dir_name、online(bool)、game_mode、pvp、max_players、max_snapshots、cluster_password、cluster_intention、token(在线服)、created_at、desired_status(running/stopped,开机对账用)、status(实际状态)。
- `shards`:id、instance_id、role(master/secondary)、shard_dir_name(Master/Caves/…)、is_master、server_port、master_server_port、authentication_port、master_port、**pid、fifo_path、log_path、last_started_at**、status、worldgen_preset。
- `mods`:id、instance_id、workshop_id、name、enabled、source(workshop/manual)、config_json(逐 MOD 的 configuration_options)、title、installed_time_updated(更新基线)、workshop_time_updated、last_checked。
- `mod_configs`:id、shard_id、mod_id、option_key、option_value(每 Shard 的 modoverrides 配置项)。
- `access_entries`:id、instance_id、kind(admin/whitelist/blocklist)、klei_id(KU_/OU_)、note —— 渲染为 adminlist.txt/whitelist.txt/blocklist.txt(见 1.3)。
- `backups`:id、instance_id、type(file)、trigger(manual/auto/pre-restore/pre-update)、path、size、created_at、note。
- `kv`:全局键值(`backup_auto_enabled`/`backup_interval_min`/`backup_retention` 等)。
- `settings`(全局单例):安装根 `base_dir`、`steamcmd_dir`、`server_dir`、`ugc_mods_dir`、`conf_dir`、默认端口池范围等。
- `proxy_config`(全局单例,或并入 `settings`):id、enabled、mode(off/env/force)、scheme(http/https/socks5)、host、port、username、password(加密存储)、no_proxy、updated_at。仅用于下载/更新场景。
- (鉴权已去除)本服务**部署在内网,不做认证/鉴权**;如日后需要,再补 `users` / `audit_logs`。

### 3.4 关键操作的实现序列(供编码参考)

**启动一个带洞穴的实例**:
1. 校验配置(3.1 全部约束)→ 2. 渲染并写回所有 ini/lua 到 `clusters/<cluster>/` → 3. 跑 updater 子进程(`-only_update_server_mods`,可叠加代理)→ 4. 建 FIFO/日志,`Popen` 起 Master 子进程(cwd=`server/bin64`)并 tail 日志等 `Sim paused` → 5. 同法起 Caves 子进程等"与 Master 互联成功" → 6. 写 PID 文件,标记 instance=running。

**回滚**:`c_save()`(可选)→ 文件级备份当前(可选)→ `c_rollback(n)` 或"停服→覆盖目录→启服" → 校验启动就绪。

**更新 MOD**:停 Shard(`c_shutdown(true)`)→ 跑 updater(`-only_update_server_mods`)→ 重启 Shard(`-skip_update_server_mods`)→ 校验 MOD 加载日志。

---

## 附:权威来源

- Klei 官方:Dedicated Server Command Line Options Guide;Dedicated Server Settings Guide(cluster.ini / server.ini 全量项,作者为 Klei 开发者)。
- Don't Starve 官方 Wiki:Guides/Don't Starve Together Dedicated Servers(目录结构、Cluster/Shard、V1/V2 MOD、worldgen/leveldata、安装与启用 MOD、命令行参数);Simple Dedicated Server Setup;Saving(快照/回滚);Console/Don't Starve Together Commands(控制台命令)。
- 运行参考:`superjump22/dontstarvetogether` 等成熟方案(目录布局、`-only_update_server_mods` / `-skip_update_server_mods` / `-ugc_directory` 用法)。**本方案不采用容器化**,改为宿主机用 Python `subprocess` 直接托管 Shard 进程、FIFO 注入 stdin、日志文件采集、`psutil` 监控。
- MOD 元信息:`modinfo.lua` 的 `configuration_options` 结构(name/label/options[].{description,data}/default)。