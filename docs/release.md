# 打包与发布流程(AI 智能体可照做)

> 本文目标:让任何人(或 AI 智能体)无需追问背景,就能把本项目正确打包并发布。
> 读完「关键约束」再动手 —— 那几条是最容易踩的坑。

## 两个产物

| 产物 | 文件名 | 由谁产出 | 去向 |
|---|---|---|---|
| A. 后端发布包 | `dst-serverd-x86_64-linux.tar.gz` | `build-release.sh` | 手动上传到 CNB Release(latest) |
| B. GUI 部署工具 | `dst-deployer.exe` | `gui/build.sh` | 分发给终端用户(详见 B 节) |

仓库远端:
- `cnb` → `https://cnb.cool/greenshadecapital/dst-server-icp`(**发布主战场**)
- `origin` → `https://github.com/phil616/dst-server-icp`(镜像)

---

## 关键约束(必读,最易踩坑)

1. **GitHub 不可达**。目标机在国内、CNB CI 也只走白名单网络,**任何 github URL 都不要用**。uv、Python 解释器、依赖都要走国内/CNB 渠道。
2. **没有 CI 发布**。CNB 流水线 `.cnb.yml` 已被删除(CI 连不上 github,无法构建)。发布流程是 **本地打包 → 手动在 CNB 网页上传 Release 附件**。不要试图加 CI 自动发布。
3. **Python 解释器内置**。清华 PyPI 镜像只镜像 wheel,**不提供 Python 解释器**;南京大学的 python-build-standalone 镜像**已下架**(对其 URL 发请求可能返回 2xx 但文件实际不存在,别被骗)。所以发布包内置一份 standalone Python(`python/bin/python3.12`),`install-dst.sh` 用 `UV_PYTHON=<绝对路径>` + `UV_PYTHON_DOWNLOADS=never` 直接用它,绝不联网下载解释器。
4. **uv 从 CNB 镜像取**:`https://cnb.cool/dreamreflex/localize-uv/-/releases/latest/download/`(只放 uv,不放 Python)。
5. **CNB Release 资产 HEAD 返回 400**。验证下载**必须用 GET**(`curl -fL ... -o file`),`curl -I`(HEAD)会误报失败。
6. **raw 脚本直链格式**是 `/-/git/raw/main/<path>`,例如安装脚本:
   `https://cnb.cool/greenshadecapital/dst-server-icp/-/git/raw/main/install-dst.sh`
   (`/-/raw/main/` 和 `/-/blob/main/?raw=true` 返回的是 HTML 页面,不是裸文件。)
7. **若将来真要写 `.cnb.yml`**:内联 `script:` 块由 **sh(dash)** 执行,不能用 bashism(`set -o pipefail`、`[[ ]]`、数组)。用 `set -eu` + `[ ]`,bash 专属逻辑放进独立 `.sh` 文件并显式 `bash xxx.sh`。

---

## A. 发布后端管理器(`dst-serverd-x86_64-linux.tar.gz`)

### 前置条件(构建机)
- 有网络、能访问清华源
- 装了 **node/npm**(构建前端)与 **uv**
- 架构 x86_64(i686 同理,资产名变 `dst-serverd-i686-linux.tar.gz`)

### 步骤

```bash
# 1. (可选)更新版本号
#    pyproject.toml 的 version = "X.Y.Z"

# 2. 打包(首次或前端有改动加 --rebuild-frontend)
bash build-release.sh                  # 复用已构建前端
bash build-release.sh --rebuild-frontend   # 强制重建前端

# 产物:dist/dst-serverd-x86_64-linux.tar.gz
#   含:源码 + uv.lock + 已构建前端(src/dst_serverd/static) + 内置 standalone Python(python/bin/python3.12)
```

### 步骤 3:本地全流程自测(强烈建议,发布前验证包能装)

```bash
# 用 file:// 把刚打的包直接喂给安装脚本,跳过下载,跑真实安装流程
sudo DST_RELEASE_BASE="file://$(pwd)/dist" \
     DST_RELEASE_ASSET="dst-serverd-x86_64-linux.tar.gz" \
     bash install-dst.sh install
# 验证:systemctl status dst-serverd ; curl -I http://127.0.0.1:8000/
```

### 步骤 4:打 tag 并推送

```bash
git tag vX.Y.Z
git push cnb vX.Y.Z
git push origin vX.Y.Z   # 镜像(可选)
```
> 标签约定:`vX.Y.Z`(现有:`v0.2.0`、`v1.0.0`)。`pyproject` 的 version 可能滞后于 tag,以 tag 为发布依据。

### 步骤 5:在 CNB 网页发布 Release(**手动,无法脚本化**)
1. 打开 `https://cnb.cool/greenshadecapital/dst-server-icp` → **Releases**
2. 基于刚推的 tag **新建 Release**,勾选 **「设为最新 / latest」**
3. 上传 `dist/dst-serverd-x86_64-linux.tar.gz` 作为附件,**文件名保持不变**(`install-dst.sh` 按此名拉取)

### 步骤 6:验证发布(用 GET,不要用 HEAD)

```bash
URL=https://cnb.cool/greenshadecapital/dst-server-icp/-/releases/latest/download/dst-serverd-x86_64-linux.tar.gz
curl -fL "$URL" -o /tmp/check.tar.gz && sha256sum /tmp/check.tar.gz
# 与本地 dist/ 下文件的 sha256 比对一致即成功;gzip -t /tmp/check.tar.gz 应无报错
```

### 终端用户如何安装(发布完成后)

```bash
curl -fL https://cnb.cool/greenshadecapital/dst-server-icp/-/git/raw/main/install-dst.sh -o install-dst.sh
sudo bash install-dst.sh install      # 安装
sudo bash install-dst.sh update       # 升级(保留游戏/存档/数据库)
sudo bash install-dst.sh uninstall    # 卸载(保留游戏/缓存)
# 可选:mirror=<pypi镜像> 覆盖默认清华源
```

---

## B. 构建 GUI 部署工具(`dst-deployer.exe`)

面向不懂 Linux 的用户:填 SSH 四元组即可远程跑上面的 `install-dst.sh`。代码在 `gui/`。

### 前置条件(构建机)
- **Go 1.26+**
- 交叉编译 Windows 需 **mingw-w64**:`sudo apt-get install -y gcc-mingw-w64-x86-64`
  (Fyne 依赖 CGO,故交叉编译需要 C 交叉编译器)

### 步骤

```bash
cd gui
bash build.sh            # 交叉编译 → dist/dst-deployer.exe(单 exe,-H windowsgui 无控制台)
bash build.sh --native   # 仅本机平台(调试用)
```

### 注意
- `build.sh` 在编译前会**自动把仓库根的 `install-dst.sh` 同步进 `gui/scripts/`**,再经 `go:embed` 打进 exe。
  → **改了 `install-dst.sh` 必须重新 `bash build.sh`**,exe 里的脚本才会更新。
- `gui/dist/` 已被 `gui/.gitignore` 忽略,exe 不入库。
- 分发方式(**待定/建议**):可把 `dst-deployer.exe` 作为附件一并上传到上面同一个 CNB Release;或单独提供下载。此项目前未固化,发布前确认。

---

## 给 AI 智能体的一句话任务模板

> 「把后端打包并发布 vX.Y.Z:`bash build-release.sh` → 本地 file:// 自测 → `git tag vX.Y.Z && git push cnb vX.Y.Z` → 提醒我去 CNB 网页基于该 tag 建 Release(latest)并上传 `dist/dst-serverd-x86_64-linux.tar.gz` → 我传完后用 GET 校验 sha256。」

> 「重新构建 GUI:`cd gui && bash build.sh`,产物 `gui/dist/dst-deployer.exe`。」

**智能体红线**:不要用 github URL;不要加 CI 自动发布;不要用 HEAD 校验 CNB 资产;Release 的网页上传步骤只能由人完成,智能体负责打包、自测、打 tag、给出校验命令。
