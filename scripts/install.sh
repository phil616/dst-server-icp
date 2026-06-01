#!/usr/bin/env bash
# 离线安装器(目标机、root 运行)。把自包含运行时装到 /opt/dst-serverd,
# 写配置、建专用用户、装并启动 systemd 服务。全程不联网。
#
# 用法:  sudo ./install.sh            # 安装并 enable --now
#         sudo ./install.sh --uninstall  # 停服并移除 unit(保留 /opt 数据与配置)
#  可选环境变量:DST_PREFIX(默认 /opt/dst-serverd)、DST_USER(默认 dst)、DST_PORT(默认 8000)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${DST_PREFIX:-/opt/dst-serverd}"
CFG_DIR="/etc/dst-serverd"
CFG="$CFG_DIR/config.yaml"
SERVICE="/etc/systemd/system/dst-serverd.service"
RUN_USER="${DST_USER:-dst}"
PORT="${DST_PORT:-8000}"

[ "$(id -u)" = "0" ] || { echo "✗ 请用 root 运行:sudo ./install.sh"; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  systemctl disable --now dst-serverd 2>/dev/null || true
  rm -f "$SERVICE"
  systemctl daemon-reload
  echo "✓ 已停服并移除 unit。数据/配置保留于 $DEST 与 $CFG_DIR(如需彻底删除请手动 rm -rf)。"
  exit 0
fi

[ -x "$DIR/python/bin/python3" ] || { echo "✗ 找不到自包含运行时 $DIR/python,包是否完整?"; exit 1; }

echo "==> [1/5] 专用用户 $RUN_USER"
if ! id "$RUN_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$DEST/home" --shell /usr/sbin/nologin "$RUN_USER" \
    || useradd --system "$RUN_USER"
fi

echo "==> [2/5] 安装运行时到 $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/python"
cp -a "$DIR/python" "$DEST/python"
mkdir -p "$DEST/data"

echo "==> [3/5] 配置 $CFG"
mkdir -p "$CFG_DIR"
if [ -f "$CFG" ]; then
  echo "    已存在,保留不覆盖。"
else
  SECRET="$(head -c16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  cat > "$CFG" <<EOF
# dst-serverd 配置(离线安装自动生成)
base: $DEST/data
conf_dir: clusters
host: 0.0.0.0
port: $PORT
db: $DEST/data/dstd.sqlite3
secret_key: $SECRET

# 接口鉴权:留空=不保护;填值后所有 /api 请求须带匹配的 APIKey 头(前端会弹页输入)
api_key: ""

shutdown_grace: 30
sigterm_grace: 10
EOF
  echo "    已生成(base=$DEST/data, host=0.0.0.0, port=$PORT)。"
fi

echo "==> [4/5] 属主归 $RUN_USER"
chown -R "$RUN_USER":"$RUN_USER" "$DEST" "$CFG_DIR"

echo "==> [5/5] 安装 systemd 服务"
cat > "$SERVICE" <<EOF
[Unit]
Description=DST Serverd — DST 服务器管理后端(离线自包含)
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$DEST
Environment=DSTD_CONFIG=$CFG
# 主 PID 即 Python;-m 启动后由 run() 读取 config.yaml 的 host/port
ExecStart=$DEST/python/bin/python3 -m dst_serverd.main
Restart=always
RestartSec=3
# 关键:重启/停止后端只杀 Python,不连带杀 Shard 游戏进程(玩家不掉线)
KillMode=process
TimeoutStopSec=20
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now dst-serverd

echo
echo "✅ 安装完成。访问 http://<本机IP>:$PORT/"
echo "   状态:systemctl status dst-serverd"
echo "   日志:journalctl -u dst-serverd -f"
echo "   配置:$CFG(改后 systemctl restart dst-serverd)"
