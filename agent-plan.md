# DST 游戏服务器管理项目 AI 部署代理技术方案

**文档版本**：1.0  
**适用场景**：饥荒联机版（Don't Starve Together）游戏服务器管理项目的自动化部署与运维代理系统  

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [整体架构设计](#2-整体架构设计)
3. [SSH MCP 执行层选型](#3-ssh-mcp-执行层选型)
4. [工具层接口设计](#4-工具层接口设计)
5. [Bootstrap 部署脚本规范](#5-bootstrap-部署脚本规范)
6. [Agent Loop 设计](#6-agent-loop-设计)
7. [实施路径](#7-实施路径)

---

## 1. 背景与目标

### 1.1 问题描述

DST 游戏服务器管理项目的部署涉及以下复杂操作序列：

- 以 root 身份通过 SteamCMD 下载 Steam 运行时库；
- 安装 uv（Python 环境管理器）并完成依赖同步；
- 安装 Node.js / npm 并构建前端资产；
- 从 GitHub 或 Gitea 拉取项目代码；
- 配置 systemd 单元文件并启用服务；
- 动态开放 UDP 端口（防火墙配置）。

上述步骤对目标用户群（无运维经验的游戏玩家）构成较高操作门槛。人工引导方式成本高、错误率高。

### 1.2 解决思路

引入 AI 部署代理系统，以自然语言为交互界面，将上述部署步骤自动化。用户仅需提供：

- Linux 服务器四元组：`host`、`port`、`user`、`password`；
- OpenAI API Key。

代理系统负责其余全部部署与管理操作。

### 1.3 设计约束

| 约束条件 | 说明 |
|----------|------|
| 目标环境 | Linux 服务器，具备 root 权限，预装 sshd |
| 容错策略 | 故障时由运营商重置磁盘镜像，无生产级可用性要求 |
| 资源限制 | Linux 端不引入常驻重量级 Agent 进程 |
| 控制端环境 | Windows 桌面应用程序 |
| LLM 接口 | OpenAI API（function calling） |

---

## 2. 整体架构设计

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                    Windows 控制端                         │
│                                                           │
│  ┌─────────────┐    ┌──────────────────┐    ┌─────────┐ │
│  │  桌面 GUI    │───▶│   Agent Loop     │───▶│ OpenAI  │ │
│  │ (用户输入)   │    │ (Function Call)  │    │   API   │ │
│  └─────────────┘    └────────┬─────────┘    └─────────┘ │
│                               │                           │
│                      ┌────────▼─────────┐                │
│                      │  工具层（Tool Layer）│               │
│                      │  宏工具 + 原始执行  │               │
│                      └────────┬─────────┘                │
│                               │ SSH / SFTP               │
└───────────────────────────────┼─────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────┐
│                   Linux 服务器端                           │
│                                                           │
│   sshd（唯一前提条件）                                      │
│                                                           │
│   部署后：systemd 管理的应用服务进程                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 核心设计原则

**原则一：确定性逻辑与智能逻辑分离**

所有已知的部署步骤（安装 uv、拉取代码、配置 systemd 等）均编写为幂等的 shell 脚本，与 Agent 解耦。LLM 不负责生成安装命令，仅负责编排步骤顺序、解析执行结果、处理异常分支。

**原则二：Linux 端零常驻进程**

部署阶段无需在 Linux 端安装任何 Agent 组件，仅通过 SSH 推送并执行脚本。SSH daemon 即为全部执行基础设施。如需持续监控，可在项目启动后由 systemd 托管一个轻量状态上报进程，与部署流程严格解耦。

**原则三：宏工具优先于裸 Shell**

不向 LLM 暴露自由的 shell 执行权限作为主要工具。所有已知操作封装为参数化宏工具，裸 shell 仅作为调试逃生通道，避免 LLM 自由组合 shell 命令带来的不稳定性。

---

## 3. SSH MCP 执行层选型

### 3.1 候选方案对比

| 项目 | 语言 | 内存占用 | 认证方式 | 文件传输 | 可扩展性 | 适用场景 |
|------|------|----------|----------|----------|----------|----------|
| **ssh-mcp**（mingyang91） | Rust | ~1.8 MB | 密钥 / 密码 | 否（需另行实现） | 低（闭合二进制） | 对体积有极致要求、不修改源码 |
| **remoteShell-mcp**（chouzz） | Python | 低 | 密码 / 密钥 | 是（SFTP） | 高（Python 可直接扩展） | **推荐**，直接对应四元组模型 |
| **mcp-ssh-manager**（bvisible） | TypeScript | 中 | 密码 / 密钥 / agent | 是 | 中 | 需要 DevOps 全功能工具集 |
| **tufantunc/ssh-mcp** | TypeScript | 低 | 密码 / 密钥 | 否 | 低 | 轻量 TypeScript 栈 |
| **自定义（FastMCP + Paramiko）** | Python | 极低 | 全部支持 | 是 | 最高 | **最优选**，工具集完全受控 |

### 3.2 推荐方案

**优先推荐：自定义 FastMCP + Paramiko 方案**

理由如下：

- 工具集与业务逻辑强绑定（DST 部署场景工具固定，通用 SSH MCP 存在不必要的接口噪声）；
- 项目主体为 Python，扩展成本最低；
- FastMCP 框架极轻量，最终产物为单个 Python 脚本，部署到 Windows 端无额外依赖；
- 工具接口完全可控，便于实现宏工具（见第 4 节）。

**次选：remoteShell-mcp**

若不希望自行编写 MCP Server，remoteShell-mcp 在密码认证 + SFTP 上传下载方面开箱即用，与四元组输入模型完全吻合，可作为快速验证阶段的替代方案。

### 3.3 MCP 层是否必要

MCP 协议是标准化的工具暴露规范，非强制依赖。若 Windows 控制端直接使用 Python（如 Tkinter / wxPython），可直接以 `asyncssh` 或 `paramiko` 封装工具函数，作为 OpenAI function calling 的 handler，省去 MCP 这一进程间通信层，降低复杂度。

---

## 4. 工具层接口设计

### 4.1 设计策略

工具层划分为两类：

- **宏工具（Macro Tools）**：对应已知业务操作，命令实现写死在工具内部，LLM 仅传递参数；
- **原始工具（Raw Tools）**：暴露受限的裸 shell 执行能力，仅用于异常诊断。

正常部署流程 **全程使用宏工具**，原始工具作为排错逃生通道。

### 4.2 工具清单

#### 宏工具

```python
# 执行指定 Bootstrap 步骤（幂等）
bootstrap(step: str) -> StepResult
# step 枚举值：
#   "check_env"        - 检测发行版、架构、磁盘空间
#   "install_uv"       - 安装 uv
#   "install_node"     - 安装 Node.js / npm（通过 fnm）
#   "clone_repo"       - 从 GitHub / Gitea 克隆代码
#   "install_deps"     - uv sync + npm install + npm run build
#   "setup_systemd"    - 写入 systemd 单元文件并 enable
#   "start_services"   - systemctl start 全部服务
#   "check_services"   - 返回各服务运行状态

# 开放指定 UDP 端口（ufw / firewalld 自适应）
open_udp_port(port: int) -> Result

# 关闭指定 UDP 端口
close_udp_port(port: int) -> Result

# systemd 服务控制
service(name: str, action: Literal["start","stop","restart","status","enable","disable"]) -> Result

# 读取服务日志（journalctl）
read_log(unit: str, lines: int = 50) -> str

# 上传文件到 Linux 端（SFTP）
upload(local_path: str, remote_path: str) -> Result

# 下载文件到 Windows 端（SFTP）
download(remote_path: str, local_path: str) -> Result
```

#### 原始工具（受限使用）

```python
# 执行任意 shell 命令（仅用于诊断，不在正常流程中调用）
exec(command: str, timeout: int = 60) -> ShellResult
```

### 4.3 StepResult 结构

```python
@dataclass
class StepResult:
    step: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    # 结构化标记，由脚本通过 ::STEP:<name>:<ok|err>:: 输出
    markers: list[str]
```

`bootstrap()` 工具解析脚本输出中的结构化标记，将执行结果以结构化形式返回给 LLM，避免 LLM 直接解析长文本 stderr。

---

## 5. Bootstrap 部署脚本规范

### 5.1 脚本设计要求

| 要求 | 说明 |
|------|------|
| 幂等性 | 每个步骤可重复执行，不产生副作用 |
| 发行版兼容 | 检测 apt / dnf / pacman，自动适配包管理器 |
| 结构化输出 | 每个步骤完成后输出 `::STEP:<name>:<ok\|err>::` 标记 |
| 错误分级 | 区分可重试错误（网络超时）和不可重试错误（架构不兼容） |
| 无交互 | 全程 `DEBIAN_FRONTEND=noninteractive`，不依赖 tty |

### 5.2 标记规范

```bash
# 成功标记
echo "::STEP:install_uv:ok::"

# 失败标记（附错误摘要）
echo "::STEP:install_uv:err::curl_failed_exit_code_7"
```

控制端 `bootstrap()` 工具通过正则提取标记，无需解析全量日志。

### 5.3 关键步骤实现要点

**发行版检测**

```bash
detect_distro() {
    if command -v apt-get &>/dev/null; then PKG="apt"; 
    elif command -v dnf &>/dev/null; then PKG="dnf";
    elif command -v pacman &>/dev/null; then PKG="pacman";
    else echo "::STEP:check_env:err::unsupported_distro"; exit 1; fi
}
```

**uv 安装（幂等）**

```bash
install_uv() {
    if command -v uv &>/dev/null; then
        echo "::STEP:install_uv:ok::already_installed"; return
    fi
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.local/bin/env"
    echo "::STEP:install_uv:ok::"
}
```

**Node.js 安装（通过 fnm，避免发行版老版本问题）**

```bash
install_node() {
    if command -v node &>/dev/null; then
        echo "::STEP:install_node:ok::already_installed"; return
    fi
    curl -fsSL https://fnm.vercel.app/install | bash
    source "$HOME/.local/share/fnm/env"
    fnm install --lts
    fnm use lts-latest
    echo "::STEP:install_node:ok::"
}
```

**systemd 单元文件生成（参数化）**

Bootstrap 脚本接收环境变量 `PROJECT_DIR`、`SERVICE_NAME`，动态生成 unit 文件：

```bash
setup_systemd() {
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=DST Server Manager - ${SERVICE_NAME}
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/.venv/bin/python -m your_module
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    echo "::STEP:setup_systemd:ok::"
}
```

**动态 UDP 端口处理策略**

两种可选策略：

- **策略 A（推荐）**：项目启动后将实际端口写入固定路径（如 `/var/run/dst-manager/ports.json`），`open_udp_port` 工具读取后逐一放行；
- **策略 B（简化）**：预定义一个 UDP 端口段（如 10999–11010），Bootstrap 阶段一次性全部放行，无需运行时交互。

---

## 6. Agent Loop 设计

### 6.1 框架选型

不使用 OpenCode、Claude Code、Aider 等面向代码仓库的编程 Agent，此类工具携带大量无关的 git diff、文件树管理逻辑，资源开销不符合本场景需求。

推荐方案（按复杂度排序）：

| 方案 | 适用情形 |
|------|----------|
| OpenAI Agents SDK（原生） | 仅依赖 OpenAI，无额外框架依赖，代码量最小 |
| smolagents（HuggingFace） | 需要 Code Agent 模式（直接执行 Python 代码而非 JSON tool call） |
| Pydantic AI | 需要强类型工具接口校验 |

**推荐：OpenAI Agents SDK + 原生 function calling**，依赖最少，调试最直接。

### 6.2 System Prompt 设计

System Prompt 须包含以下内容：

```
## 角色定义
作为 DST 服务器部署代理，负责在用户提供的 Linux 服务器上完成项目的部署和运维管理。

## 标准部署流程（按序执行）
1. bootstrap("check_env")          - 环境检测
2. bootstrap("install_uv")         - 安装 uv
3. bootstrap("install_node")       - 安装 Node.js
4. bootstrap("clone_repo")         - 拉取代码
5. bootstrap("install_deps")       - 安装依赖、构建前端
6. bootstrap("setup_systemd")      - 配置 systemd
7. bootstrap("start_services")     - 启动服务
8. bootstrap("check_services")     - 验证运行状态
9. 读取端口配置，调用 open_udp_port() 逐一开放

## 异常处理规则
- 步骤失败时，调用 read_log() 获取详细日志后再决策
- 网络错误（exit code 7、28）：重试当前步骤，最多 3 次
- 依赖冲突：调用 exec() 进行诊断，分析后制定修复命令
- 不可恢复错误：以清晰的中文告知用户具体原因和建议操作

## 用户交互规范
- 每个步骤开始和完成时，用非技术语言向用户说明当前进度
- 出现错误时，先诊断再汇报，不直接暴露原始 stderr
- 运维管理请求（重启、查日志、改端口）通过对应宏工具处理
```

### 6.3 Loop 流程

```
用户输入四元组 + API Key
    │
    ▼
建立 SSH 连接（Paramiko）
    │
    ▼
上传 bootstrap.sh 至 /tmp/dst_bootstrap.sh
    │
    ▼
┌─────────────────────────────────────────┐
│              Agent Loop                  │
│                                           │
│  用户消息 → OpenAI API（含工具 schema）   │
│      │                                   │
│      ▼                                   │
│  LLM 返回 tool_calls                     │
│      │                                   │
│      ▼                                   │
│  执行工具 → 返回 tool_result             │
│      │                                   │
│      └── 追加至 messages 继续循环         │
│                                           │
│  直至 LLM 返回纯文本（finish_reason:stop）│
└─────────────────────────────────────────┘
    │
    ▼
向用户展示最终状态
```

---

## 7. 实施路径

### 7.1 开发顺序

按以下顺序开发，每步独立可验证：

**Phase 1：Bootstrap 脚本验证**  
编写 `bootstrap.sh`，在测试 Linux 环境中手动 SSH 执行，验证各步骤幂等性和标记输出的正确性。此阶段不涉及 AI，纯脚本调试。

**Phase 2：工具层实现**  
实现 FastMCP Server 或直接以 Paramiko 封装工具函数。编写工具单元测试，验证 `bootstrap()`、`service()`、`open_udp_port()` 等接口行为正确。

**Phase 3：Agent Loop 集成**  
接入 OpenAI API，完成 function calling schema 定义和 system prompt 调试。使用真实 Linux 服务器进行端到端部署测试。

**Phase 4：Windows 桌面 GUI 封装**  
将上述逻辑封装为桌面应用。推荐使用以下方案：
- **Tauri（Rust + WebView）**：体积最小（< 5 MB），适合分发；
- **PyInstaller + Tkinter / wxPython**：若控制端逻辑已为 Python，打包最便捷；
- **Electron**：生态最成熟，体积较大。

### 7.2 关键文件结构

```
dst-deploy-agent/
├── bootstrap/
│   └── install.sh              # 幂等部署脚本
├── agent/
│   ├── tools.py                # 工具层实现（Paramiko 封装）
│   ├── mcp_server.py           # FastMCP Server（可选）
│   ├── loop.py                 # OpenAI Agent Loop
│   └── prompts.py              # System Prompt 常量
├── gui/
│   └── main.py                 # Windows 桌面 GUI 入口
└── tests/
    └── test_tools.py           # 工具层单元测试
```

### 7.3 可交付的代码产物清单

如需进一步落地，可基于本方案生成以下代码产物：

- `bootstrap/install.sh`：完整幂等部署脚本（含发行版自适应、结构化标记输出）；
- `agent/tools.py`：完整工具层实现（含 `bootstrap()`、`service()`、`open_udp_port()` 等宏工具）；
- `agent/loop.py`：OpenAI function calling Agent Loop 骨架；
- `agent/mcp_server.py`：基于 FastMCP 的 SSH MCP Server 实现（如采用 MCP 架构）。

---

*本方案不涉及 DST 服务器本身的配置逻辑（集群 token、分片配置、mod 管理等），上述内容由管理项目自身处理。*