#!/usr/bin/env bash
# =============================================================================
# install-dst.sh — dst-serverd(饥荒服务器管理后端)一键安装 / 升级 / 卸载脚本
#
# 必须以 root 在 Linux 上执行。安装后由 systemd 托管。
#
#   bash install-dst.sh install              # 安装管理器本体
#   bash install-dst.sh update               # 升级管理器本体(保留游戏/存档/数据库)
#   bash install-dst.sh uninstall            # 卸载管理器本体(保留游戏、steamcmd、uv、缓存)
#
# 可选参数 mirror(PyPI 镜像,默认清华源,默认不使用官方 PyPI):
#   bash install-dst.sh install mirror=https://pypi.tuna.tsinghua.edu.cn/simple
#   bash install-dst.sh install --mirror https://mirrors.aliyun.com/pypi/simple
#
# 国内网络约束:
#   - uv 从固定 CNB 镜像下载(无法走 github)
#   - PyPI 走镜像源(默认清华)
#   - 前端为预构建产物,随发布包下发,不安装 node/npm
# =============================================================================
set -euo pipefail

# ------------------------------- 可配置变量 ----------------------------------
# 项目发布包(release latest);含已构建前端、config.yaml 模板、uv.lock,解压即可 uv sync。
# 可用环境变量 DST_RELEASE_BASE 覆盖(例如指向自建/内网镜像)。
RELEASE_BASE="${DST_RELEASE_BASE:-https://cnb.cool/greenshadecapital/dst-server-icp/-/releases/latest/download}"

# uv 本地化发布包(国内可达,替代 github 的 astral.sh)。
UV_RELEASE_BASE="${DST_UV_RELEASE_BASE:-https://cnb.cool/dreamreflex/localize-uv/-/releases/latest/download}"

# 默认 PyPI 镜像(清华)。可被 mirror 参数覆盖,但不允许官方 pypi.org。
DEFAULT_MIRROR="https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"

# Python 解释器策略:发布包内置 standalone Python(python-build-standalone),
# uv 直接使用它,绝不联网下载解释器(国内无可靠的 python-build-standalone 镜像)。
# 内置解释器在发布包内的相对路径;可用 DST_BUNDLED_PYTHON 指定绝对路径覆盖。
BUNDLED_PYTHON_REL="${DST_BUNDLED_PYTHON_REL:-python/bin/python3.12}"

# --------------------------------- 路径布局 ----------------------------------
INSTALL_DIR="/opt/dst-serverd"            # 源码目录(update 时整体替换)
CONFIG_DIR="/etc/dst-serverd"             # 配置(持久,跨升级保留)
CONFIG_FILE="$CONFIG_DIR/config.yaml"
DATA_DIR="/var/lib/dst-serverd"           # 面板 SQLite 数据库(持久,跨升级保留)
DST_BASE="/opt/dst"                       # 游戏/SteamCMD/MOD/存档根(持久,卸载也保留)
UV_CACHE_DIR="/var/cache/dst-serverd/uv"  # uv 全局缓存=已下载的第三方包(卸载保留,便于离线重建)
UV_BIN="/usr/local/bin/uv"
UVX_BIN="/usr/local/bin/uvx"
RUN_USER="dst"
SERVICE_NAME="dst-serverd"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
HTTP_PORT="8000"                          # 面板监听端口

# --------------------------------- 工具函数 ----------------------------------
log()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" = "0" ] || die "必须以 root 运行:sudo bash install-dst.sh $*"
}

# 下载 URL 到指定文件,优先 curl,回退 wget。
download() {
  local url="$1" out="$2"
  log "下载 $url"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --retry-delay 2 -o "$out" "$url" \
      || die "下载失败:$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -t 3 -O "$out" "$url" \
      || die "下载失败:$url"
  else
    die "未找到 curl 或 wget,无法下载。请先安装其一。"
  fi
}

# 探测 CPU 架构,设定 uv 与项目发布包的资产名。
detect_arch() {
  local m; m="$(uname -m)"
  case "$m" in
    x86_64|amd64)
      UV_ASSET="uv-x86_64-unknown-linux-gnu.tar.gz"
      PROJ_ARCH="x86_64" ;;
    i386|i486|i586|i686)
      UV_ASSET="uv-i686-unknown-linux-gnu.tar.gz"
      PROJ_ARCH="i686" ;;
    *)
      die "不支持的架构:$m(仅支持 x86_64 / i686)" ;;
  esac
  # 项目发布包资产名(随架构);可用 DST_RELEASE_ASSET 覆盖。
  PROJECT_ASSET="${DST_RELEASE_ASSET:-dst-serverd-${PROJ_ARCH}-linux.tar.gz}"
}

# 解析参数:第 1 个非 flag 为动作;mirror 支持 mirror=URL / --mirror URL。
ACTION=""
MIRROR="$DEFAULT_MIRROR"
parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      install|update|uninstall)
        [ -z "$ACTION" ] || die "只能指定一个动作(install/update/uninstall)"
        ACTION="$1" ;;
      mirror=*)   MIRROR="${1#mirror=}" ;;
      --mirror)   shift; MIRROR="${1:-}" ;;
      -h|--help)  usage; exit 0 ;;
      *)          die "未知参数:$1(用法见 --help)" ;;
    esac
    shift
  done
  [ -n "$ACTION" ] || { usage; die "缺少动作参数:install / update / uninstall"; }
  # 兜底:任何空/官方 pypi 都回退到默认镜像。
  case "$MIRROR" in
    ""|*pypi.org*) warn "镜像非法或为空,回退默认清华源"; MIRROR="$DEFAULT_MIRROR" ;;
  esac
}

usage() {
  cat <<'EOF'
用法: bash install-dst.sh <install|update|uninstall> [mirror=URL]

  install    安装 dst-serverd 管理器本体并交由 systemd 启动
  update     停服 → 删除源码目录 → 重新下载发布包 → 重装(保留游戏/存档/数据库)
  uninstall  停服并删除源码目录与 systemd 单元(保留游戏、steamcmd、uv、第三方包缓存)

  mirror=URL PyPI 镜像源,默认 https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
EOF
}

# 创建专用运行用户。
ensure_user() {
  if ! id "$RUN_USER" >/dev/null 2>&1; then
    log "创建专用用户 $RUN_USER"
    useradd --system --create-home --home-dir "/home/$RUN_USER" \
            --shell /usr/sbin/nologin "$RUN_USER" \
      || useradd --system "$RUN_USER" \
      || die "创建用户 $RUN_USER 失败"
  fi
}

# 安装 SteamCMD 所需的 32 位运行库。
# SteamCMD 是 32 位程序(steamcmd.sh 实际执行 linux32/steamcmd),在 64 位系统上若缺少
# i386 版 glibc/gcc 运行库,会报 `linux32/steamcmd: cannot execute: required file not found`
# (32 位动态链接器 /lib/ld-linux.so.2 不存在),导致「装/更 服务端本体」失败 rc=127。
# best-effort:面板本体跑 64 位内置 Python、并不依赖它,故装失败不致命,仅告警并给出手动命令。
# 仅 x86_64 需要(i686 主机本就是 32 位,steamcmd 原生运行)。
ensure_steam_deps() {
  [ "$PROJ_ARCH" = "x86_64" ] || return 0
  log "安装 SteamCMD 32 位运行库(i386 glibc/gcc)"
  if command -v apt-get >/dev/null 2>&1; then
    dpkg --add-architecture i386 >/dev/null 2>&1 || true
    apt-get update -y >/dev/null 2>&1 || warn "apt-get update 失败,仍尝试安装 32 位库"
    if apt-get install -y lib32gcc-s1 libc6:i386 >/dev/null 2>&1 \
       || apt-get install -y lib32gcc1 libc6:i386 >/dev/null 2>&1; then
      log "32 位运行库已就绪(apt)"
    else
      warn "apt 安装失败,请手动:dpkg --add-architecture i386 && apt update && apt install -y lib32gcc-s1 libc6:i386"
    fi
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y glibc.i686 libstdc++.i686 >/dev/null 2>&1 \
      && log "32 位运行库已就绪(dnf)" \
      || warn "dnf 安装失败,请手动:dnf install -y glibc.i686 libstdc++.i686"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y glibc.i686 libstdc++.i686 >/dev/null 2>&1 \
      && log "32 位运行库已就绪(yum)" \
      || warn "yum 安装失败,请手动:yum install -y glibc.i686 libstdc++.i686"
  elif command -v zypper >/dev/null 2>&1; then
    zypper install -y glibc-32bit libstdc++6-32bit >/dev/null 2>&1 \
      && log "32 位运行库已就绪(zypper)" \
      || warn "zypper 安装失败,请手动安装 glibc-32bit libstdc++6-32bit"
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm lib32-glibc lib32-gcc-libs >/dev/null 2>&1 \
      && log "32 位运行库已就绪(pacman)" \
      || warn "pacman 安装失败,请先启用 multilib 仓库再手动:pacman -S lib32-glibc lib32-gcc-libs"
  else
    warn "未识别包管理器,无法自动安装 SteamCMD 32 位库。请手动安装 i386 版 glibc/gcc,否则装游戏本体会报 'cannot execute: required file not found'"
  fi
}

# 从固定镜像安装 uv(幂等)。
install_uv() {
  if [ -x "$UV_BIN" ]; then
    log "uv 已存在($("$UV_BIN" --version 2>/dev/null || echo unknown)),跳过下载"
    return
  fi
  local tmp; tmp="$(mktemp -d)"
  download "${UV_RELEASE_BASE}/${UV_ASSET}" "$tmp/uv.tar.gz"
  log "解压安装 uv 到 /usr/local/bin"
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp"
  # 包内通常为 <asset-name-without-ext>/uv,uvx;兜底用 find 定位。
  local uv_path uvx_path
  uv_path="$(find "$tmp" -type f -name uv | head -n1)"
  uvx_path="$(find "$tmp" -type f -name uvx | head -n1)"
  [ -n "$uv_path" ] || die "uv 发布包内未找到 uv 可执行文件"
  install -m 0755 "$uv_path" "$UV_BIN"
  [ -n "$uvx_path" ] && install -m 0755 "$uvx_path" "$UVX_BIN" || true
  rm -rf "$tmp"
  log "uv 安装完成:$("$UV_BIN" --version)"
}

# 写项目级 uv 配置:指定 PyPI 镜像为默认且唯一索引(屏蔽官方 pypi)。
write_uv_config() {
  log "配置项目 PyPI 镜像:$MIRROR"
  cat > "$INSTALL_DIR/uv.toml" <<EOF
# 由 install-dst.sh 生成。国内 PyPI 镜像作为默认且唯一索引,禁用官方 pypi.org。
# 不下载托管 Python:解释器由发布包内置,经 UV_PYTHON / UV_PYTHON_DOWNLOADS=never 指定。
[[index]]
url = "$MIRROR"
default = true
EOF
}

# 下载项目发布包并展开到 INSTALL_DIR。
fetch_project() {
  local tmp; tmp="$(mktemp -d)"
  download "${RELEASE_BASE}/${PROJECT_ASSET}" "$tmp/project.tar.gz"
  log "解压发布包到 $INSTALL_DIR"
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR" "$tmp/extract"
  tar -xzf "$tmp/project.tar.gz" -C "$tmp/extract"
  # 兼容“包内单顶层目录”与“直接平铺文件”两种结构:以 pyproject.toml 所在目录为源根。
  local src="$tmp/extract"
  if [ ! -f "$src/pyproject.toml" ]; then
    local sub; sub="$(find "$tmp/extract" -maxdepth 2 -name pyproject.toml | head -n1)"
    [ -n "$sub" ] || die "发布包内未找到 pyproject.toml,包结构异常"
    src="$(dirname "$sub")"
  fi
  cp -a "$src/." "$INSTALL_DIR/"
  rm -rf "$tmp"
  [ -f "$INSTALL_DIR/pyproject.toml" ] || die "展开后缺少 pyproject.toml"
  [ -f "$INSTALL_DIR/uv.lock" ] || warn "发布包缺少 uv.lock,将无法 --frozen 同步"
}

# 生成持久化 config.yaml(仅首次;已存在则保留用户设置)。
render_config() {
  mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$DST_BASE"
  if [ -f "$CONFIG_FILE" ]; then
    log "已存在配置 $CONFIG_FILE,保留不覆盖"
    return
  fi
  log "生成配置 $CONFIG_FILE"
  local secret; secret="$(head -c16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  cat > "$CONFIG_FILE" <<EOF
# dst-serverd 配置(install-dst.sh 自动生成)。绝对路径,确保升级后数据/存档不丢。
base: $DST_BASE
conf_dir: clusters

host: 0.0.0.0
port: $HTTP_PORT
db: $DATA_DIR/dstd.sqlite3
secret_key: $secret

# 接口鉴权:留空=不保护(内网任意访问);填值后所有 /api 请求须带匹配的 APIKey 头。
api_key: ""

shutdown_grace: 30
sigterm_grace: 10
EOF
}

# 解析要使用的 Python 解释器(优先发布包内置 standalone,回退系统 python3.12)。
# 须在 fetch_project 之后调用。结果存入全局 PYTHON_BIN。
PYTHON_BIN=""
resolve_python() {
  PYTHON_BIN=""
  if [ -n "${DST_BUNDLED_PYTHON:-}" ] && [ -x "${DST_BUNDLED_PYTHON}" ]; then
    PYTHON_BIN="$DST_BUNDLED_PYTHON"
  elif [ -x "$INSTALL_DIR/$BUNDLED_PYTHON_REL" ]; then
    PYTHON_BIN="$INSTALL_DIR/$BUNDLED_PYTHON_REL"
  else
    # 兜底:在 python/bin 下匹配任意 python3*。
    local c; c="$(ls "$INSTALL_DIR"/python/bin/python3* 2>/dev/null | sort | head -n1 || true)"
    [ -n "$c" ] && PYTHON_BIN="$c"
  fi
  if [ -z "$PYTHON_BIN" ]; then
    if command -v python3.12 >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v python3.12)"
      warn "发布包内未发现内置 Python,回退系统 python3.12:$PYTHON_BIN"
    else
      die "未找到 Python 解释器:发布包应内置 standalone Python($BUNDLED_PYTHON_REL),且系统也无 python3.12"
    fi
  fi
  log "使用 Python 解释器:$PYTHON_BIN"
}

# uv sync 构建 .venv(以运行用户身份,使用持久化缓存;解释器固定为 PYTHON_BIN,禁止联网下载)。
sync_deps() {
  log "uv sync 同步依赖(镜像:$MIRROR,缓存:$UV_CACHE_DIR)"
  local sync_args="--frozen --no-dev"
  [ -f "$INSTALL_DIR/uv.lock" ] || sync_args="--no-dev"

  chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR" "$UV_CACHE_DIR"
  sudo -u "$RUN_USER" env \
       HOME="/home/$RUN_USER" \
       UV_CACHE_DIR="$UV_CACHE_DIR" \
       UV_PYTHON="$PYTHON_BIN" \
       UV_PYTHON_DOWNLOADS=never \
       "$UV_BIN" sync $sync_args --directory "$INSTALL_DIR" \
    || die "uv sync 失败(检查镜像 $MIRROR 是否可达,解释器 $PYTHON_BIN 是否可用)"
}

# 写并启用 systemd 单元。
write_service() {
  log "安装 systemd 单元 $SERVICE_FILE"
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=DST Serverd — 饥荒服务器管理后端
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$INSTALL_DIR
Environment=DSTD_CONFIG=$CONFIG_FILE
Environment=UV_CACHE_DIR=$UV_CACHE_DIR
Environment=HOME=/home/$RUN_USER
# 解释器固定为发布包内置 Python,禁止 uv 联网下载
Environment=UV_PYTHON=$PYTHON_BIN
Environment=UV_PYTHON_DOWNLOADS=never
# 启动前同步锁定依赖(幂等,命中缓存极快);前端产物已随发布包整合进 static/
ExecStartPre=$UV_BIN sync --frozen --no-dev --directory $INSTALL_DIR
# 主 PID 即 Python;run() 读取 config.yaml 的 host/port 绑定
ExecStart=$INSTALL_DIR/.venv/bin/python -m dst_serverd.main
Restart=always
RestartSec=3
# 关键:重启/停止后端只杀 Python 主进程,不连带杀 Shard 游戏进程(玩家不掉线)
KillMode=process
TimeoutStopSec=20
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
}

# 修正属主。
fix_ownership() {
  chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR" "$DST_BASE" "$UV_CACHE_DIR"
}

# 尽力放行面板端口(防火墙存在才操作,失败不致命)。
open_firewall() {
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi active; then
    ufw allow "${HTTP_PORT}/tcp" >/dev/null 2>&1 && log "ufw 放行 ${HTTP_PORT}/tcp" || true
  elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="${HTTP_PORT}/tcp" >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 && log "firewalld 放行 ${HTTP_PORT}/tcp" || true
  fi
}

# --------------------------------- 三大动作 ----------------------------------
do_install() {
  log "开始安装 dst-serverd(架构:$PROJ_ARCH)"
  mkdir -p "$UV_CACHE_DIR" "$DATA_DIR" "$DST_BASE"
  ensure_user
  ensure_steam_deps   # SteamCMD 32 位运行库,缺则装游戏本体会 rc=127
  install_uv
  fetch_project
  resolve_python
  write_uv_config
  render_config
  sync_deps
  write_service
  fix_ownership
  open_firewall
  log "启用并启动服务"
  systemctl enable --now "$SERVICE_NAME"
  echo
  log "✅ 安装完成"
  cat <<EOF
   访问:  http://<本机IP>:${HTTP_PORT}/
   状态:  systemctl status ${SERVICE_NAME}
   日志:  journalctl -u ${SERVICE_NAME} -f
   配置:  ${CONFIG_FILE}(改后 systemctl restart ${SERVICE_NAME})
   游戏根:${DST_BASE}   数据库:${DATA_DIR}
EOF
}

do_update() {
  log "开始升级 dst-serverd(保留游戏/存档/数据库/配置)"
  if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
    log "停止服务(仅停面板,不杀游戏进程)"
    systemctl stop "$SERVICE_NAME" || true
  fi
  ensure_steam_deps   # 幂等;补装早期版本漏掉的 SteamCMD 32 位运行库
  install_uv          # 幂等,uv 已存在则跳过
  fetch_project       # 内部会 rm -rf 旧源码目录后重新下载展开
  resolve_python
  write_uv_config
  render_config       # 已有配置则保留
  sync_deps
  write_service
  fix_ownership
  log "重新启动服务"
  # 用 restart 而非 enable --now:enable --now 末尾是 start,对"仍在运行"的服务是空操作,
  # 一旦上面第 ~344 行的 stop 没真正停掉旧进程(|| true 吞错),升级后会继续跑旧代码
  # (static 读盘看着是新的,后端逻辑仍是旧的)。restart 原子且无条件替换进程,确保加载新代码。
  systemctl enable "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"
  echo
  log "✅ 升级完成"
}

do_uninstall() {
  log "卸载 dst-serverd 管理器本体(保留游戏、steamcmd、uv、第三方包缓存)"
  if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
    systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
  fi
  rm -rf "$INSTALL_DIR"
  echo
  log "✅ 已卸载源码与服务单元"
  cat <<EOF
   已保留:游戏与存档 ${DST_BASE}
           面板数据库 ${DATA_DIR}
           配置文件   ${CONFIG_DIR}
           uv 二进制  ${UV_BIN}
           第三方包   ${UV_CACHE_DIR}
   如需彻底清除上述内容请手动 rm -rf。
   重新安装:bash install-dst.sh install
EOF
}

# ----------------------------------- 主流程 ----------------------------------
main() {
  parse_args "$@"
  require_root "$ACTION"
  detect_arch
  case "$ACTION" in
    install)   do_install ;;
    update)    do_update ;;
    uninstall) do_uninstall ;;
  esac
}

main "$@"
