# dst-deployer — 饥荒服务器部署 GUI

面向**不熟悉 Linux 的用户**的图形化部署工具。填入 SSH 四元组(主机 / 端口 / 用户 / 密码),
即可把项目内置的 `install-dst.sh` 在远端 Linux 上执行,完成:

- **测试连接** —— 验证四元组并读取系统信息
- **系统准备(apt)** —— `apt-get update`(可选 `upgrade`)+ 确保 `curl` 已装
- **安装管理器** —— 远端执行 `install-dst.sh install`
- **升级管理器** —— `install-dst.sh update`(保留游戏/存档/数据库)
- **卸载管理器** —— `install-dst.sh uninstall`(保留游戏与缓存)
- **服务状态** —— `systemctl status dst-serverd`

## 关键设计

- **单一 exe**:Fyne GUI 静态链接,产物为单个 `dst-deployer.exe`,双击即用,无控制台窗口。
- **内置脚本**:`install-dst.sh` 通过 `go:embed` 打进 exe,运行时经 SFTP 上传到目标机
  `/tmp/dst-install.sh` 再执行 —— 不依赖目标机能访问 CNB 抓脚本,版本始终与本程序一致。
- **JSON 持久化**:连接与偏好存于 `<用户配置目录>/dst-deployer/config.json`(0600 权限),
  可手动编辑。Windows 路径:`%AppData%\dst-deployer\config.json`。
- **日志隐私遮挡**:运行日志写 `<用户配置目录>/dst-deployer/logs/deploy-YYYY-MM-DD.log`,
  并实时显示在界面。**主机、用户、密码在写入前一律被替换为 `******`**,避免四元组泄漏。
- **sudo 提权**:登录用户非 `root` 时,勾选项会以 `sudo -S` 提权,密码经 stdin 喂给 sudo
  (不出现在命令行/进程列表)。

> 安全说明:为降低门槛,SSH 连接当前不校验主机密钥(等同首次自动信任)。仅在可信网络使用。
> `config.json` 含明文密码,请妥善保管该文件。

## 构建

需要 Go 1.26+。交叉编译 Windows 版还需 mingw-w64(Fyne 依赖 CGO)。

```bash
# 交叉编译 Windows x64 单 exe -> dist/dst-deployer.exe
bash build.sh

# 仅本地平台(调试)
bash build.sh --native
```

Debian/Ubuntu 安装交叉编译器:

```bash
sudo apt-get install -y gcc-mingw-w64-x86-64
```

`build.sh` 会在编译前自动把仓库根目录的 `install-dst.sh` 同步进 `scripts/`,确保内置脚本最新。

## 目录结构

```
gui/
  main.go              程序入口(加载配置/日志,启动窗口)
  embed.go             go:embed 内置 install-dst.sh
  scripts/install-dst.sh   构建时从 ../install-dst.sh 同步而来
  build.sh             构建脚本(交叉编译 / 本地)
  internal/
    config/   JSON 配置与连接 Profile 的读写
    logx/     带隐私遮挡的日志器(文件 + UI 双写)
    sshx/     SSH 连接、命令流式执行、SFTP 上传
    deploy/   把各部署动作编排成高层方法
    ui/       Fyne 主窗口与交互
```
