#!/usr/bin/env bash
# 构建「完全离线、解压即跑」的自包含发布包(在有网的构建机上执行一次)。
#
# 产物 dist/dst-serverd-<ver>-linux-x86_64.tar.gz 内含:
#   python/   可重定位的独立 CPython 3.12 + dst_serverd + 全部依赖 + 预构建前端(static)
#   install.sh / run.sh / config.yaml.example / VERSION / README-OFFLINE.md
# 目标机无需联网、无需 Python/uv/Node/pip,U 盘拷过去解压即可部署。
#
# 用法:  scripts/build-bundle.sh           # 完整构建(含前端)
#         SKIP_WEB=1 scripts/build-bundle.sh  # 跳过前端构建(沿用已存在的 static/)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ARCH="x86_64"
PYVER="3.12"
VER="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)"
NAME="dst-serverd-${VER}-linux-${ARCH}"
OUT="$ROOT/dist"
STAGE="$OUT/$NAME"
PY="$STAGE/python/bin/python3"

command -v uv >/dev/null || { echo "✗ 需要 uv(仅构建机需要)"; exit 1; }

echo "==> 清理 $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"

echo "==> [1/5] 构建前端并整合进 static/"
if [ "${SKIP_WEB:-0}" = "1" ] && [ -f "$ROOT/src/dst_serverd/static/index.html" ]; then
  echo "    SKIP_WEB=1,沿用已存在的 static/"
else
  "$ROOT/make-web.sh"
fi
[ -f "$ROOT/src/dst_serverd/static/index.html" ] || { echo "✗ static/ 未构建"; exit 1; }

echo "==> [2/5] 获取可重定位的独立 Python ${PYVER}(python-build-standalone)"
export UV_PYTHON_PREFERENCE=only-managed   # 必须用 uv 托管的独立构建,绝不用系统 python(不可重定位)
uv python install "$PYVER"
SRC_PY="$(uv python find "$PYVER")"
SRC_HOME="$(dirname "$(dirname "$SRC_PY")")"
echo "    源解释器:$SRC_HOME"
cp -a "$SRC_HOME" "$STAGE/python"

echo "==> [3/5] 把项目+锁定依赖安装进独立 Python(从 uv.lock)"
# uv pip install --python <解释器> 直接装进该独立 Python 的 site-packages,
# 无需其内置 pip/ensurepip,也不污染系统环境。
uv export --frozen --no-dev --no-emit-project --no-hashes -o "$OUT/requirements.txt"
uv pip install --python "$PY" -r "$OUT/requirements.txt"
uv pip install --python "$PY" --no-deps "$ROOT"

echo "==> [4/5] 复制运行文件 + 生成说明"
cp "$ROOT/config.yaml.example" "$STAGE/config.yaml.example"
cp "$ROOT/scripts/install.sh"  "$STAGE/install.sh"
cp "$ROOT/scripts/run.sh"      "$STAGE/run.sh"
chmod +x "$STAGE/install.sh" "$STAGE/run.sh"
echo "$VER" > "$STAGE/VERSION"
cat > "$STAGE/README-OFFLINE.md" <<EOF
# dst-serverd 离线部署包 v$VER (linux-$ARCH)

完全自包含:已内置 Python 运行时、依赖与前端,目标机**无需联网/Python/Node**。

## 方式一:systemd 常驻(推荐,需 root)
\`\`\`bash
sudo ./install.sh            # 安装到 /opt/dst-serverd 并 enable --now
sudo ./install.sh --uninstall  # 卸载服务(保留数据)
\`\`\`
装好后访问 http://<本机IP>:8000/ 。配置在 /etc/dst-serverd/config.yaml。

## 方式二:当前目录直接前台运行(免 root,快速试跑)
\`\`\`bash
./run.sh
\`\`\`
首次会在本目录生成 config.yaml,按需改 base/port/api_key 后重跑。

注:DST 本体/SteamCMD/MOD 仍需运行时从 Steam 拉取(可在面板「代理设置」里配代理)。
EOF

echo "==> [5/5] 自检 + 打包"
"$PY" -c "import dst_serverd, pathlib, sys
from dst_serverd.main import app
st = pathlib.Path(dst_serverd.__file__).parent / 'static' / 'index.html'
assert st.exists(), '✗ 打包内缺少前端 static/index.html'
print('    自检通过:dst_serverd 可导入,static 已内置,python', sys.version.split()[0])"

tar -C "$OUT" -czf "$OUT/${NAME}.tar.gz" "$NAME"
SIZE="$(du -h "$OUT/${NAME}.tar.gz" | cut -f1)"
echo
echo "✅ 完成:$OUT/${NAME}.tar.gz ($SIZE)"
echo "   上传到 GitHub Release(或拷进 U 盘),目标机解压后 sudo ./install.sh 即可。"
