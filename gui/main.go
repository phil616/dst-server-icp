// dst-deployer:面向 Windows 的图形化部署工具。
//
// 通过输入 SSH 四元组(主机/端口/用户/密码),把项目内置的 install-dst.sh
// 在远端 Linux 上执行,实现:系统准备(apt)、安装 / 升级 / 卸载管理器。
// 配置以 JSON 持久化,操作日志写文件并自动遮挡四元组关键信息。
package main

import (
	"log"

	"dst-deployer/internal/config"
	"dst-deployer/internal/logx"
	"dst-deployer/internal/ui"

	"fyne.io/fyne/v2/app"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("加载配置失败: %v", err)
	}

	baseDir, err := config.Dir()
	if err != nil {
		log.Fatalf("定位程序目录失败: %v", err)
	}
	logger, err := logx.New(baseDir, nil) // sink 在 UI 构建后挂接
	if err != nil {
		log.Fatalf("初始化日志失败: %v", err)
	}
	defer logger.Close()

	a := app.NewWithID("cool.dreamreflex.dst-deployer")
	w := ui.Build(a, cfg, logger, installScript)
	w.ShowAndRun()
}
