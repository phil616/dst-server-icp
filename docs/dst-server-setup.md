# Don't Starve Together 专用服务器部署指南

**适用环境：** Ubuntu / Debian · 公网 VPS · 地面 + 洞穴双 shard · 无 MOD

---

## 目录

1. [准备环境](#1-准备环境)
2. [安装 SteamCMD](#2-安装-steamcmd)
3. [下载 DST 服务端](#3-下载-dst-服务端)
4. [配置集群](#4-配置集群)
5. [创建启动脚本](#5-创建启动脚本)
6. [验证与日常管理](#6-验证与日常管理)

---

## 1. 准备环境

### 1.1 创建专用系统用户

强烈建议为游戏服务器单独建立低权限用户，避免以 root 运行。

```bash
# 创建用户（家目录 /home/steam，bash shell）
sudo useradd -m -s /bin/bash steam

# 为其设置密码（推荐）
sudo passwd steam
```

### 1.2 安装系统依赖

SteamCMD 依赖 32 位库，以 root 或 sudo 权限执行：

```bash
sudo dpkg --add-architecture i386
sudo apt-get update
sudo apt-get install -y \
  lib32gcc-s1 \
  libstdc++6 \
  libstdc++6:i386 \
  curl \
  wget \
  screen \
  ca-certificates
```

> **注意：** Ubuntu 22.04+ 中 `lib32gcc-s1` 替代了旧版 `lib32gcc1`，若报包名错误请改用 `lib32gcc1`。

### 1.3 开放防火墙端口

双 shard 需要以下 UDP 端口，在 ufw 和 VPS 控制面板安全组中同时放行：

```bash
sudo ufw allow 10999/udp    # Overworld shard（对外）
sudo ufw allow 10998/udp    # Caves shard（对外）
sudo ufw allow 10888/udp    # Master shard IPC（内部通信）
sudo ufw reload
```

| 端口  | 协议 | 用途                  |
|-------|------|-----------------------|
| 10999 | UDP  | Overworld shard 对外  |
| 10998 | UDP  | Caves shard 对外      |
| 10888 | UDP  | 两个 shard 内部通信   |

> **重要：** 阿里云、腾讯云、AWS 等平台除 ufw 外，还需在控制台的**安全组**中单独添加上述 UDP 入站规则。

---

## 2. 安装 SteamCMD

切换到 steam 用户后执行所有后续操作：

```bash
sudo su - steam
```

下载并安装 SteamCMD：

```bash
mkdir -p ~/steamcmd
cd ~/steamcmd

curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" \
  | tar zxf - -C ~/steamcmd

# 首次运行，自动完成 SteamCMD 自身的更新
~/steamcmd/steamcmd.sh +quit
```

看到 `Loading Steam API... OK` 即代表安装成功。

---

## 3. 下载 DST 服务端

DST 专用服务端（AppID **343050**）匿名登录即可免费下载，无需购买游戏：

```bash
mkdir -p ~/dst_server

~/steamcmd/steamcmd.sh \
  +force_install_dir ~/dst_server \
  +login anonymous \
  +app_update 343050 validate \
  +quit
```

> 首次下载约 **2 GB**，视网速需几分钟至十几分钟。看到 `Success! App '343050' fully installed.` 即完成。

验证可执行文件存在：

```bash
ls ~/dst_server/bin64/
# 应看到：dontstarve_dedicated_server_nullrenderer_x64
```

---

## 4. 配置集群

### 4.1 获取 Cluster Token

公网服务器必须有 Token，否则启动会报 `E_INVALID_TOKEN`。

在**本地电脑**的 DST 游戏中操作（而非服务器）：

1. 启动 DST 客户端
2. 按 `~` 键打开开发者控制台
3. 输入以下命令并回车：

```
TheNet:GenerateClusterToken()
```

Token 文件保存位置：

- **Windows：** `%USERPROFILE%\Documents\Klei\DoNotStarveTogether\cluster_token.txt`
- **macOS：** `~/Documents/Klei/DoNotStarveTogether/cluster_token.txt`

将文件中的内容（一长串字符）复制备用。

### 4.2 创建配置目录结构

```bash
mkdir -p ~/.klei/DoNotStarveTogether/MyCluster/Master
mkdir -p ~/.klei/DoNotStarveTogether/MyCluster/Caves
mkdir -p ~/logs
```

最终目录结构：

```
~/.klei/DoNotStarveTogether/MyCluster/
├── cluster.ini             # 集群主配置
├── cluster_token.txt       # Klei 账号 Token
├── Master/                 # Overworld shard
│   ├── server.ini
│   └── worldgenoverride.lua
└── Caves/                  # Caves shard
    ├── server.ini
    └── worldgenoverride.lua
```

### 4.3 写入 cluster_token.txt

```bash
# 将 YOUR_TOKEN_HERE 替换为实际 token 字符串
echo "YOUR_TOKEN_HERE" > ~/.klei/DoNotStarveTogether/MyCluster/cluster_token.txt
```

### 4.4 创建 cluster.ini（集群主配置）

```bash
cat > ~/.klei/DoNotStarveTogether/MyCluster/cluster.ini << 'EOF'
[GAMEPLAY]
game_mode           = survival
max_players         = 6
pvp                 = false
pause_when_empty    = true

[NETWORK]
cluster_name        = My DST Server
cluster_description = Dedicated Server
cluster_password    =
cluster_intention   = cooperative
lan_only_cluster    = false

[MISC]
console_enabled     = true

[SHARD]
shard_enabled       = true
bind_ip             = 127.0.0.1
master_ip           = 127.0.0.1
master_port         = 10888
cluster_key         = my_secret_key
EOF
```

**关键参数说明：**

| 参数 | 说明 | 可选值 |
|------|------|--------|
| `game_mode` | 游戏模式 | `survival` / `endless` / `wilderness` |
| `cluster_password` | 服务器密码，留空为无密码 | 任意字符串 |
| `cluster_intention` | 游戏风格标签 | `cooperative` / `competitive` / `social` / `madness` |
| `cluster_key` | 两 shard 间认证密钥，可任意填写但两侧必须一致 | 任意字符串 |

### 4.5 创建 Master/server.ini（Overworld shard）

```bash
cat > ~/.klei/DoNotStarveTogether/MyCluster/Master/server.ini << 'EOF'
[NETWORK]
server_port = 10999

[SHARD]
is_master   = true
name        = Master

[STEAM]
master_server_port  = 27018
authentication_port = 8768
EOF
```

### 4.6 创建 Caves/server.ini（洞穴 shard）

```bash
cat > ~/.klei/DoNotStarveTogether/MyCluster/Caves/server.ini << 'EOF'
[NETWORK]
server_port = 10998

[SHARD]
is_master     = false
name          = Caves
shard_enabled = true

[STEAM]
master_server_port  = 27019
authentication_port = 8769
EOF
```

### 4.7 创建世界生成配置

**地面层（Master）：**

```bash
cat > ~/.klei/DoNotStarveTogether/MyCluster/Master/worldgenoverride.lua << 'EOF'
return {
  override_enabled = true,
  preset = "SURVIVAL_TOGETHER",
}
EOF
```

**洞穴层（Caves）：**

```bash
cat > ~/.klei/DoNotStarveTogether/MyCluster/Caves/worldgenoverride.lua << 'EOF'
return {
  override_enabled = true,
  preset = "DST_CAVE",
}
EOF
```

---

## 5. 创建启动脚本

### 5.1 启动脚本 start_dst.sh

脚本使用 `screen` 在后台分别启动两个 shard：

```bash
cat > ~/start_dst.sh << 'SCRIPT'
#!/bin/bash
set -e

DST_BIN=~/dst_server/bin64/dontstarve_dedicated_server_nullrenderer_x64
CLUSTER=MyCluster
CONF_DIR=~/.klei/DoNotStarveTogether

echo "==> 启动 Overworld (Master) shard..."
screen -dmS dst_master bash -c "
  cd ~/dst_server/bin64 && \
  ${DST_BIN} \
    -cluster ${CLUSTER} \
    -conf_dir ${CONF_DIR} \
    -shard Master \
    -console \
  2>&1 | tee ~/logs/dst_master.log
"

sleep 3

echo "==> 启动 Caves shard..."
screen -dmS dst_caves bash -c "
  cd ~/dst_server/bin64 && \
  ${DST_BIN} \
    -cluster ${CLUSTER} \
    -conf_dir ${CONF_DIR} \
    -shard Caves \
    -console \
  2>&1 | tee ~/logs/dst_caves.log
"

echo "==> 两个 shard 已在后台运行"
echo "    查看 Master 日志: screen -r dst_master"
echo "    查看 Caves 日志:  screen -r dst_caves"
SCRIPT

chmod +x ~/start_dst.sh
```

### 5.2 停止脚本 stop_dst.sh

```bash
cat > ~/stop_dst.sh << 'SCRIPT'
#!/bin/bash
echo "==> 向 Master shard 发送 c_shutdown()..."
screen -S dst_master -p 0 -X stuff "c_shutdown()$(printf '\r')"
sleep 2
echo "==> 向 Caves shard 发送 c_shutdown()..."
screen -S dst_caves  -p 0 -X stuff "c_shutdown()$(printf '\r')"
sleep 2
screen -wipe
echo "==> 已发送关闭指令"
SCRIPT

chmod +x ~/stop_dst.sh
```

### 5.3 首次启动

```bash
~/start_dst.sh
```

> **注意：** 首次启动会自动生成世界地图，耗时约 1~3 分钟，期间 CPU 会跑满，属于正常现象，等待即可。

---

## 6. 验证与日常管理

### 6.1 确认启动成功

进入 Master shard 控制台查看日志：

```bash
screen -r dst_master
```

成功标志（按顺序出现）：

```
[Steam] Game server SteamID: xxxxxxxxxxxxxxxxx
...
Sim paused
```

看到 `Sim paused` 代表世界已生成，服务器正在等待玩家连接。

> **退出控制台但保持后台运行：** 按 `Ctrl+A`，然后按 `D`（分离 screen）。直接关闭终端或按 `Ctrl+C` 会终止进程。

### 6.2 常用管理命令

```bash
# 查看所有后台 screen 会话
screen -ls

# 进入 Master / Caves 控制台
screen -r dst_master
screen -r dst_caves

# 停止服务器
~/stop_dst.sh

# 重启服务器
~/stop_dst.sh && sleep 3 && ~/start_dst.sh

# 更新服务端版本
~/steamcmd/steamcmd.sh \
  +force_install_dir ~/dst_server \
  +login anonymous \
  +app_update 343050 validate \
  +quit
```

### 6.3 游戏内控制台命令

在 screen 控制台中可直接输入游戏命令（按回车执行）：

| 命令 | 作用 |
|------|------|
| `c_save()` | 手动存档 |
| `c_shutdown()` | 安全关闭当前 shard |
| `c_regenerateworld()` | 重新生成世界 |
| `c_rollback(1)` | 回滚 1 天存档 |
| `TheNet:Kick("用户名")` | 踢出指定玩家 |
| `c_announce("消息")` | 向所有玩家发送公告 |

### 6.4 （推荐）设置 systemd 开机自启

以 root 权限创建服务文件，使服务器在 VPS 重启后自动恢复运行：

```bash
sudo tee /etc/systemd/system/dst.service > /dev/null << 'EOF'
[Unit]
Description=Don't Starve Together Dedicated Server
After=network.target

[Service]
Type=forking
User=steam
ExecStart=/home/steam/start_dst.sh
ExecStop=/home/steam/stop_dst.sh
RemainAfterExit=yes
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable dst      # 设置开机自启
sudo systemctl start dst       # 立即启动
sudo systemctl status dst      # 查看运行状态
```

---

## 常见问题排查

| 现象 | 原因 | 解决方法 |
|------|------|----------|
| `E_INVALID_TOKEN` | cluster_token.txt 内容有误或为空 | 重新生成 token 并覆盖写入 |
| 服务器在游戏列表中找不到 | 防火墙端口未放行 | 检查 ufw 和云平台安全组的 UDP 10999 规则 |
| Caves 无法连接 Overworld | cluster.ini 中 `cluster_key` 两边不一致 | 确保 Master 和 Caves 的 cluster_key 完全相同 |
| 启动后立即崩溃 | 缺少 32 位依赖库 | 重新执行 `apt-get install lib32gcc-s1` |
| 世界生成卡住超过 10 分钟 | 内存不足（低于 1.5 GB） | 升级服务器配置或减少 `max_players` |

---

*推荐最低配置：2 核 CPU · 2 GB RAM · 10 GB SSD · Ubuntu 20.04+*
