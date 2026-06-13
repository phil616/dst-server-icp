# dst-deployer Qt GUI

C++ / Qt Widgets 版桌面前端。它不包含部署逻辑,而是调用 Go 构建出的
`dst-deployer-core`。这样可以直接产出原生 EXE,同时复用现有 SSH、部署、
防火墙、配置和日志遮挡代码。

## 一键构建

```bash
cd /path/to/dst-serverd
bash build-qt.sh
```

产物会输出到:

```text
dist/dst-deployer-qt/
  dst-deployer-qt
  dst-deployer-core
```

Windows 下文件名为 `dst-deployer-qt.exe` 和 `dst-deployer-core.exe`。
发布给其他 Windows 机器前,脚本会在找到 `windeployqt` 时自动复制 Qt 运行库。

## 依赖

### Linux / Ubuntu

安装依赖:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake qt6-base-dev
```

可选安装 Ninja 加速构建:

```bash
sudo apt-get install -y ninja-build
```

### Windows

推荐直接在 Windows 上构建 EXE。安装:

- Go
- Git for Windows
- Qt 6,选择 MinGW 套件或 MSVC 套件
- CMake
- Ninja

确保 `go`、`cmake`、`ninja`、`windeployqt` 在 PATH 中,然后在 Git Bash 里运行:

```bash
cd /c/path/to/dst-serverd
bash build-qt.sh
```

产物目录:

```text
dist/dst-deployer-qt/
  dst-deployer-qt.exe
  dst-deployer-core.exe
  Qt6*.dll
  platforms/
```

不建议在 Linux 上直接交叉编译 Qt Windows EXE。Go core 可以交叉编译,
但 Qt GUI 需要一整套 Windows Qt SDK、插件和运行库部署流程,在 Windows
原生环境或 Windows CI 中构建更稳定。

## GitHub Actions 发版产物

推送 `v*` tag 或手动运行 `Build Release Assets` workflow 会自动上传:

- `dst-serverd-x86_64-linux.tar.gz`: `build-release.sh` 生成的服务端更新包
- `dst-deployer-qt-linux-x86_64.tar.gz`: Linux Qt GUI 包,内含 GUI 程序和 Go core
- `dst-deployer-qt-windows-x86_64-setup.exe`: Windows 单文件安装器,内含 Qt GUI、Go core 和 Qt 运行库

## 已覆盖功能

- 连接配置保存、删除、选择
- 测试连接、系统准备、安装、升级、卸载、服务状态
- 防火墙检测、放行端口、关闭防火墙
- PyPI 镜像、sudo、apt upgrade 偏好
- 实时日志、取消操作、打开日志目录
