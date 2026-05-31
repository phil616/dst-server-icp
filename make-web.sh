#!/usr/bin/env bash
# 构建前端并整合到后端静态目录,实现单项目启动(后端直接托管前端,无需 dev 服务器)。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATIC="$ROOT/src/dst_serverd/static"

echo "==> [1/3] 安装前端依赖(npm install)"
cd "$ROOT/frontend"
if [ -f package-lock.json ]; then
  npm ci || npm install
else
  npm install
fi

echo "==> [2/3] 构建前端(npm run build)"
npm run build

echo "==> [3/3] 整合构建产物到 $STATIC"
rm -rf "$STATIC"
mkdir -p "$STATIC"
cp -r dist/. "$STATIC/"

echo
echo "✅ 前端已整合进后端。现在单项目启动即可:"
echo "   uv sync && uv run uvicorn dst_serverd.main:app --host 0.0.0.0 --port 8000"
echo "   打开 http://<host>:8000/ 即为控制台。"
