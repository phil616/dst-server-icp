#!/usr/bin/env bash
# 在解压目录内直接前台运行(免 root、免 systemd,快速试跑)。
# 首次会在本目录生成 config.yaml;Ctrl-C 退出。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -x "$DIR/python/bin/python3" ] || { echo "✗ 找不到自包含运行时 $DIR/python"; exit 1; }

if [ ! -f "$DIR/config.yaml" ]; then
  cp "$DIR/config.yaml.example" "$DIR/config.yaml"
  echo "已生成 $DIR/config.yaml,可按需修改 base/host/port/api_key 后重跑。"
fi

export DSTD_CONFIG="$DIR/config.yaml"
exec "$DIR/python/bin/python3" -m dst_serverd.main
