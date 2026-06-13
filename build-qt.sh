#!/usr/bin/env bash
# Build the Qt desktop package.
#
# Output:
#   dist/dst-deployer-qt/
#     dst-deployer-qt[.exe]
#     dst-deployer-core[.exe]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QT_SRC="$ROOT/qt_gui"
QT_BUILD="$QT_SRC/build"
OUT_DIR="$ROOT/dist/dst-deployer-qt"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[提示]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

command -v go >/dev/null 2>&1 || die "未找到 go。请先安装 Go。"
command -v cmake >/dev/null 2>&1 || die "未找到 cmake。Ubuntu: sudo apt-get install -y cmake"

if ! command -v c++ >/dev/null 2>&1 && ! command -v g++ >/dev/null 2>&1 && ! command -v clang++ >/dev/null 2>&1; then
  die "未找到 C++ 编译器。Ubuntu: sudo apt-get install -y build-essential"
fi

case "$(uname -s 2>/dev/null || printf unknown)" in
  MINGW*|MSYS*|CYGWIN*)
    EXE_SUFFIX=".exe"
    ;;
  *)
    EXE_SUFFIX=""
    ;;
esac

log "构建 Go headless core"
(cd "$ROOT/gui" && bash build.sh --core)

log "配置 Qt/CMake 项目"
rm -rf "$QT_BUILD"
mkdir -p "$QT_BUILD"

cmake_args=(-S "$QT_SRC" -B "$QT_BUILD" -DCMAKE_BUILD_TYPE=Release)
if command -v ninja >/dev/null 2>&1; then
  cmake_args+=(-G Ninja)
else
  warn "未找到 ninja,使用 CMake 默认构建器。需要 Ninja 时安装: sudo apt-get install -y ninja-build"
fi

if ! cmake "${cmake_args[@]}"; then
  cat >&2 <<'EOF'

[错误] Qt/CMake 配置失败。

Ubuntu 常见修复:
  sudo apt-get update
  sudo apt-get install -y build-essential cmake qt6-base-dev

如果 Qt 安装在自定义目录,请设置 CMAKE_PREFIX_PATH,例如:
  CMAKE_PREFIX_PATH=/opt/Qt/6.7.0/gcc_64 bash build-qt.sh
EOF
  exit 1
fi

log "编译 Qt GUI"
cmake --build "$QT_BUILD" --config Release

GUI_BIN="$QT_BUILD/dst-deployer-qt$EXE_SUFFIX"
if [ ! -f "$GUI_BIN" ] && [ -f "$QT_BUILD/Release/dst-deployer-qt$EXE_SUFFIX" ]; then
  GUI_BIN="$QT_BUILD/Release/dst-deployer-qt$EXE_SUFFIX"
fi
[ -f "$GUI_BIN" ] || die "未找到 Qt GUI 产物: dst-deployer-qt$EXE_SUFFIX"

CORE_BIN="$ROOT/gui/dist/dst-deployer-core$EXE_SUFFIX"
[ -f "$CORE_BIN" ] || die "未找到 Go core 产物: $CORE_BIN"

log "整理产物"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
cp "$GUI_BIN" "$OUT_DIR/"
cp "$CORE_BIN" "$OUT_DIR/"

if [ "$EXE_SUFFIX" = ".exe" ] && command -v windeployqt >/dev/null 2>&1; then
  log "运行 windeployqt 复制 Qt 运行库"
  windeployqt "$OUT_DIR/dst-deployer-qt.exe"
elif [ "$EXE_SUFFIX" = ".exe" ]; then
  warn "未找到 windeployqt。EXE 已生成,但发布给其他机器前需运行 windeployqt。"
fi

log "✅ 产物目录:$OUT_DIR"
ls -lh "$OUT_DIR"

