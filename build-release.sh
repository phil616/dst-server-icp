#!/usr/bin/env bash
# =============================================================================
# build-release.sh — 组装 dst-serverd 离线发布包(供 install-dst.sh 使用)。
#
# 在【有网、有 node/npm】的构建机上运行(目标机不需要)。产出:
#   dist/dst-serverd-<arch>-linux.tar.gz
# 包内含:源码 + uv.lock + 已构建前端(src/dst_serverd/static) + 内置 standalone Python。
# 解压后 install-dst.sh 用内置 Python 执行 uv sync,目标机全程不下载解释器。
#
# 用法:
#   bash build-release.sh                      # 自动取 standalone python(uv) + 复用已构建前端
#   bash build-release.sh --rebuild-frontend   # 强制重新构建前端
#   bash build-release.sh --python /path/root  # 指定 standalone python 根目录(含 bin/python3.12)
#   bash build-release.sh --pyver 3.12         # 指定 Python 版本(默认 3.12)
#   bash build-release.sh --out /tmp/out       # 指定输出目录(默认 ./dist)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ------------------------------- 参数解析 -----------------------------------
PYVER="3.12"
PYTHON_ROOT=""        # 用户指定的 standalone python 根目录
OUT_DIR="$ROOT/dist"
REBUILD_FRONTEND=0
while [ $# -gt 0 ]; do
  case "$1" in
    --rebuild-frontend) REBUILD_FRONTEND=1 ;;
    --python) shift; PYTHON_ROOT="${1:-}" ;;
    --pyver)  shift; PYVER="${1:-3.12}" ;;
    --out)    shift; OUT_DIR="${1:-$ROOT/dist}" ;;
    -h|--help) grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数:$1" >&2; exit 1 ;;
  esac
  shift
done

log()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || die "未找到 uv,请先安装 uv(构建机需要)"

# ------------------------------- 架构探测 -----------------------------------
case "$(uname -m)" in
  x86_64|amd64) ARCH="x86_64" ;;
  i386|i486|i586|i686) ARCH="i686" ;;
  *) die "不支持的架构:$(uname -m)" ;;
esac
PKG_NAME="dst-serverd-${ARCH}-linux"
STATIC="$ROOT/src/dst_serverd/static"

# ----------------------------- [1/4] 前端构建 -------------------------------
if [ "$REBUILD_FRONTEND" = "1" ] || [ ! -f "$STATIC/index.html" ]; then
  log "[1/4] 构建前端(make-web.sh)"
  command -v npm >/dev/null 2>&1 || die "构建前端需要 npm,但未找到(或用 --rebuild-frontend 前先装好 node)"
  bash "$ROOT/make-web.sh"
else
  log "[1/4] 复用已构建前端 $STATIC(加 --rebuild-frontend 可强制重建)"
fi
[ -f "$STATIC/index.html" ] || die "前端产物缺失:$STATIC/index.html"

# --------------------------- [2/4] 取 standalone Python ----------------------
log "[2/4] 准备内置 standalone Python($PYVER, $ARCH)"
if [ -n "$PYTHON_ROOT" ]; then
  PY_SRC="$(readlink -f "$PYTHON_ROOT")"
  [ -x "$PY_SRC/bin/python3.12" ] || [ -x "$PY_SRC/bin/python3" ] \
    || die "--python 指定的目录下没有 bin/python3.12:$PY_SRC"
else
  # 必须是 uv 托管的 python-build-standalone(可重定位),不能用系统 /usr 解释器。
  uv python install "$PYVER" >/dev/null 2>&1 || true
  PYDIR="$(uv python dir 2>/dev/null)"
  [ -n "$PYDIR" ] && [ -d "$PYDIR" ] || die "无法获取 uv python dir,请检查 uv 安装"
  # 在托管目录里挑匹配 版本+架构 的安装根,取最高补丁版(sort -V 末位)。
  PY_SRC="$(ls -d "$PYDIR"/cpython-${PYVER}*-linux-${ARCH}*gnu 2>/dev/null | sort -V | tail -n1 || true)"
  [ -n "$PY_SRC" ] || die "uv 托管目录无 $PYVER/$ARCH 的 standalone:先运行 'uv python install $PYVER',或用 --python 指定"
  PY_SRC="$(readlink -f "$PY_SRC")"
fi
# 防呆:绝不打包系统目录。
case "$PY_SRC/" in
  /usr/|/usr/*|/bin/|/bin/*|/) die "拒绝打包系统目录($PY_SRC);需 uv 托管的 standalone Python" ;;
esac
[ -x "$PY_SRC/bin/python3.12" ] || [ -x "$PY_SRC/bin/python3" ] || die "standalone 根目录无 bin/python3*:$PY_SRC"
log "  使用 standalone:$PY_SRC"

# ------------------------------ [3/4] 组装暂存目录 ---------------------------
log "[3/4] 组装包内容"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG_DIR="$STAGE/$PKG_NAME"
mkdir -p "$PKG_DIR"

# 源码与元数据(uv sync 所需:pyproject + lock + src 包源)。
cp -a "$ROOT/pyproject.toml" "$PKG_DIR/"
cp -a "$ROOT/uv.lock"        "$PKG_DIR/"
cp -a "$ROOT/.python-version" "$PKG_DIR/" 2>/dev/null || true
cp -a "$ROOT/README.md"      "$PKG_DIR/" 2>/dev/null || true
cp -a "$ROOT/LICENSE"        "$PKG_DIR/" 2>/dev/null || true
cp -a "$ROOT/config.yaml.example" "$PKG_DIR/" 2>/dev/null || true

# src/(含已构建 static),剔除缓存。
cp -a "$ROOT/src" "$PKG_DIR/"
find "$PKG_DIR/src" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG_DIR/src" -type d -name '*.egg-info' -prune -exec rm -rf {} + 2>/dev/null || true

# 内置 Python(保留内部相对符号链接,standalone 可重定位)。
mkdir -p "$PKG_DIR/python"
cp -a "$PY_SRC/." "$PKG_DIR/python/"
# 校验:内置解释器可执行且可重定位运行。
"$PKG_DIR/python/bin/python3.12" --version >/dev/null 2>&1 \
  || "$PKG_DIR/python/bin/python3" --version >/dev/null 2>&1 \
  || die "内置 Python 无法运行,打包中止"

# ------------------------------ [4/4] 打 tar.gz -----------------------------
log "[4/4] 打包 tar.gz"
mkdir -p "$OUT_DIR"
TARBALL="$OUT_DIR/$PKG_NAME.tar.gz"
rm -f "$TARBALL"
tar -czf "$TARBALL" -C "$STAGE" "$PKG_NAME"

SIZE="$(du -h "$TARBALL" | cut -f1)"
echo
log "✅ 发布包已生成:$TARBALL ($SIZE)"
cat <<EOF
   包内顶层目录:$PKG_NAME/
   内置解释器:  $PKG_NAME/python/bin/python3.12
   前端产物:    $PKG_NAME/src/dst_serverd/static/

   本地全流程试跑:
     # 把它当作 release 资产喂给安装脚本(用 file:// 跳过下载):
     sudo DST_RELEASE_BASE="file://$OUT_DIR" \\
          DST_RELEASE_ASSET="$PKG_NAME.tar.gz" \\
          bash install-dst.sh install

   发布(CI 无法访问 github,故本地打包后手动上传):
     1. 打 tag 并推送:git tag v0.2.0 && git push cnb v0.2.0
     2. CNB 仓库 → Releases → 基于该 tag 新建 Release,勾选「设为最新(latest)」
     3. 上传本包为附件,文件名保持 $PKG_NAME.tar.gz 不变(install-dst.sh 按此名拉取)
     4. 验证:curl -IL https://cnb.cool/greenshadecapital/dst-server-icp/-/releases/latest/download/$PKG_NAME.tar.gz
EOF
