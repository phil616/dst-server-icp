# AGENTS.md

本文件约束本仓库中的构建、打包和发布操作。涉及版本、发布包、Tag、Release、安装脚本或部署工具时，必须先阅读并遵守本文件；完整说明见 `docs/release.md`。

## 发布渠道

- `cnb` 是发布主仓库：`https://cnb.cool/greenshadecapital/dst-server-icp`。
- `origin`（GitHub）只是镜像，GitHub Actions 产物不能代替 CNB 正式发布。
- 不得把“GitHub Release 已成功”视为本项目发布完成。
- CNB 没有自动发布流水线。正式流程是：本地构建发布包、推送 CNB Tag、人工在 CNB 网页创建 Release 并上传附件。
- 不要新增 `.cnb.yml` 或 GitHub 自动发布流程，除非用户明确要求修改发布架构。

## 修改版本号

发布 `vX.Y.Z` 前，必须先将以下版本统一为 `X.Y.Z`：

- `pyproject.toml`
- `src/dst_serverd/__init__.py`
- `uv.lock`
- `frontend/package.json`
- `frontend/package-lock.json` 中项目自身的顶层版本

版本号必须在构建发布包之前修改并提交。不得先打包再改版本。

## 前端构建

- `npm run build` 只生成 `frontend/dist`，不能更新后端实际打包使用的静态文件。
- 后端使用的前端目录是 `src/dst_serverd/static`。
- 只要前端代码发生变化，发布构建必须通过以下命令执行：

```bash
bash build-release.sh --rebuild-frontend --expect-version vX.Y.Z
```

- 不得用单独的 `npm run build`、GitHub Actions 产物或已有 `src/dst_serverd/static` 代替上述发布构建。
- `build-release.sh --rebuild-frontend` 会调用 `make-web.sh`，将 `frontend/dist` 复制到 `src/dst_serverd/static`，然后再组装离线发布包。

## 后端发布包

正式后端发布产物必须由仓库根目录的 `build-release.sh` 生成：

```bash
bash build-release.sh --rebuild-frontend --expect-version vX.Y.Z
```

期望产物：

```text
dist/dst-serverd-x86_64-linux.tar.gz
```

禁止手工拼装 tar 包，禁止直接把源码目录压缩后作为 Release 资产。

## 打包后强制校验

推送 Tag 或上传 Release 前，必须完成以下检查：

```bash
tar -xzOf dist/dst-serverd-x86_64-linux.tar.gz \
  dst-serverd-x86_64-linux/pyproject.toml | grep -m1 '^version'

gzip -t dist/dst-serverd-x86_64-linux.tar.gz
sha256sum dist/dst-serverd-x86_64-linux.tar.gz
```

如果本次修改了前端或关键后端功能，还必须从 tar 包内部确认新代码和新前端文案确实存在。不能只检查 Git Tag 中的源码。

推荐在发布前执行真实安装测试：

```bash
sudo DST_RELEASE_BASE="file://$(pwd)/dist" \
     DST_RELEASE_ASSET="dst-serverd-x86_64-linux.tar.gz" \
     bash install-dst.sh install
```

未执行该测试时，交付说明中必须明确标注“未执行本地安装测试”。

## Tag 与远端

确认发布包校验通过后，才能创建和推送 Tag：

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push cnb main
git push cnb vX.Y.Z
```

GitHub 镜像可选同步：

```bash
git push origin main
git push origin vX.Y.Z
```

推送后必须核对 CNB 的 `main` 和 Tag 指向预期提交。已有同名 Tag 时不得静默覆盖或强推。

## CNB Release

CNB Release 附件上传是人工步骤，自动化智能体不能声称已经完成：

1. 打开 CNB 仓库的 Releases 页面。
2. 基于 `vX.Y.Z` 创建 Release。
3. 设置为 latest。
4. 上传 `dist/dst-serverd-x86_64-linux.tar.gz`，保持文件名不变。

只有 CNB Release 附件存在且下载校验成功，才可报告“发布完成”。

验证必须使用 GET，不能使用 HEAD：

```bash
URL=https://cnb.cool/greenshadecapital/dst-server-icp/-/releases/latest/download/dst-serverd-x86_64-linux.tar.gz
curl -fL "$URL" -o /tmp/check.tar.gz
gzip -t /tmp/check.tar.gz
sha256sum /tmp/check.tar.gz dist/dst-serverd-x86_64-linux.tar.gz
```

两个 SHA256 必须一致。CNB Release 对 HEAD 请求可能返回错误，因此禁止用 `curl -I` 判断发布结果。

## GUI 部署工具

修改 `gui/` 或 `install-dst.sh` 后，需要重新构建 GUI：

```bash
cd gui
bash build.sh
```

产物为 `gui/dist/dst-deployer.exe`。`build.sh` 会把根目录的 `install-dst.sh` 同步并嵌入 GUI；修改安装脚本后不重建 GUI 会导致部署工具携带旧脚本。

## 发布完成判定

报告发布完成前，必须同时满足：

- 所有版本文件已更新并提交。
- 本地发布包由 `build-release.sh --rebuild-frontend --expect-version` 生成。
- tar 包内版本、关键后端代码和前端静态产物已验证。
- `main` 和 Tag 已推送到 `cnb`。
- 用户已在 CNB 创建 latest Release 并上传本地构建的附件。
- CNB 下载文件与本地文件 SHA256 一致。

缺少任意一项时，只能报告当前进度和剩余步骤，不能报告“发版成功”。
