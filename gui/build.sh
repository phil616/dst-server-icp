#!/usr/bin/env bash
# =============================================================================
# build.sh — 构建 dst-deployer 单文件可执行程序。
#
# 默认在 Linux 上交叉编译出 Windows x64 单 exe(需 mingw-w64 提供的
# x86_64-w64-mingw32-gcc,Fyne 需要 CGO)。也可本地构建当前平台版本。
#
# 用法:
#   bash build.sh                 # 交叉编译 windows/amd64 -> dist/dst-deployer.exe
#   bash build.sh --native        # 构建当前平台(调试用)
#   bash build.sh --core          # 仅构建 Qt 前端使用的 headless core
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

# 同步最新的 install-dst.sh(内置进 exe),保证与项目根脚本一致。
if [ -f "$ROOT/../install-dst.sh" ]; then
  cp "$ROOT/../install-dst.sh" "$ROOT/scripts/install-dst.sh"
  cp "$ROOT/../install-dst.sh" "$ROOT/internal/assets/install-dst.sh"
  log "已同步 install-dst.sh 到 scripts/ 与 internal/assets/"
else
  die "未找到 ../install-dst.sh,请在仓库内构建"
fi

mkdir -p "$ROOT/dist"

case "$(uname -s 2>/dev/null || printf unknown)" in
  MINGW*|MSYS*|CYGWIN*)
    NATIVE_EXE_SUFFIX=".exe"
    ;;
  *)
    NATIVE_EXE_SUFFIX=""
    ;;
esac

if [ "${1:-}" = "--core" ]; then
  log "构建 headless core"
  go build -o "$ROOT/dist/dst-deployer-core${NATIVE_EXE_SUFFIX}" ./cmd/core
  log "✅ 产物:dist/dst-deployer-core${NATIVE_EXE_SUFFIX}"
  exit 0
fi

if [ "${1:-}" = "--native" ]; then
  log "本地构建当前平台"
  go build -o "$ROOT/dist/dst-deployer-core${NATIVE_EXE_SUFFIX}" ./cmd/core
  go build -o "$ROOT/dist/dst-deployer${NATIVE_EXE_SUFFIX}" .
  log "✅ 产物:dist/dst-deployer${NATIVE_EXE_SUFFIX}"
  log "✅ 产物:dist/dst-deployer-core${NATIVE_EXE_SUFFIX}"
  exit 0
fi

command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1 \
  || die "缺少 x86_64-w64-mingw32-gcc(交叉编译 Windows 需要)。Debian/Ubuntu: apt-get install gcc-mingw-w64-x86-64"

log "交叉编译 windows/amd64(单 exe,内嵌图形界面,无控制台窗口)"
CGO_ENABLED=1 GOOS=windows GOARCH=amd64 CC=x86_64-w64-mingw32-gcc \
  go build -ldflags "-H windowsgui -s -w" -o "$ROOT/dist/dst-deployer.exe" .

log "交叉编译 windows/amd64 headless core"
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 \
  go build -ldflags "-s -w" -o "$ROOT/dist/dst-deployer-core.exe" ./cmd/core

log "✅ 产物:dist/dst-deployer.exe ($(du -h "$ROOT/dist/dst-deployer.exe" | cut -f1))"
log "✅ 产物:dist/dst-deployer-core.exe ($(du -h "$ROOT/dist/dst-deployer-core.exe" | cut -f1))"
