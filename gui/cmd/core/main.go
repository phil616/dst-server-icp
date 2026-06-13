// dst-deployer-core is the headless backend used by the Qt front-end.
//
// It keeps the existing Go SSH/deploy implementation and exposes a small JSON
// interface so UI frameworks do not need to link against Go GUI libraries.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"dst-deployer/internal/assets"
	"dst-deployer/internal/config"
	"dst-deployer/internal/coreio"
	"dst-deployer/internal/deploy"
	"dst-deployer/internal/logx"
)

func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout); err != nil {
		emit(os.Stdout, coreio.Envelope{Type: "error", Message: err.Error()})
		os.Exit(1)
	}
}

func run(args []string, stdin io.Reader, stdout io.Writer) error {
	if len(args) == 0 {
		return usage()
	}
	switch args[0] {
	case "config":
		return printConfig(stdout)
	case "save-profile":
		var req coreio.SaveProfileRequest
		if err := decode(stdin, &req); err != nil {
			return err
		}
		return saveProfile(req, stdout)
	case "delete-profile":
		var req coreio.DeleteProfileRequest
		if err := decode(stdin, &req); err != nil {
			return err
		}
		return deleteProfile(req, stdout)
	case "run":
		var req coreio.RunRequest
		if err := decode(stdin, &req); err != nil {
			return err
		}
		return runOperation(req, stdout)
	default:
		return usage()
	}
}

func usage() error {
	return errors.New("用法: dst-deployer-core config | save-profile | delete-profile | run")
}

func decode(r io.Reader, v any) error {
	dec := json.NewDecoder(r)
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		return fmt.Errorf("解析请求 JSON 失败: %w", err)
	}
	return nil
}

func printConfig(stdout io.Writer) error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	path, err := config.Path()
	if err != nil {
		return err
	}
	dir, err := config.Dir()
	if err != nil {
		return err
	}
	emit(stdout, coreio.Envelope{
		Type: "config",
		Config: &coreio.ConfigResponse{
			Path:          path,
			LogDir:        filepath.Join(dir, "logs"),
			DefaultMirror: config.DefaultMirror,
			Config:        cfg,
		},
	})
	return nil
}

func saveProfile(req coreio.SaveProfileRequest, stdout io.Writer) error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	if strings.TrimSpace(req.Profile.Name) != "" {
		cfg.Upsert(req.Profile)
	}
	if req.Selected != "" {
		cfg.Selected = req.Selected
	} else if req.Profile.Name != "" {
		cfg.Selected = req.Profile.Name
	}
	cfg.Mirror = normalizeMirror(req.Mirror)
	cfg.UseSudo = req.UseSudo
	cfg.AptUpgrade = req.AptUpgrade
	if err := cfg.Save(); err != nil {
		return err
	}
	emit(stdout, coreio.Envelope{Type: "ok", Message: "配置已保存"})
	return nil
}

func deleteProfile(req coreio.DeleteProfileRequest, stdout io.Writer) error {
	name := strings.TrimSpace(req.Name)
	if name == "" {
		return errors.New("删除配置失败: 名称不能为空")
	}
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	cfg.Delete(name)
	if cfg.Selected == name {
		cfg.Selected = ""
	}
	if err := cfg.Save(); err != nil {
		return err
	}
	emit(stdout, coreio.Envelope{Type: "ok", Message: "连接已删除"})
	return nil
}

func runOperation(req coreio.RunRequest, stdout io.Writer) error {
	if err := validateRun(req); err != nil {
		return err
	}
	baseDir, err := config.Dir()
	if err != nil {
		return err
	}
	logger, err := logx.New(baseDir, func(line string) {
		emit(stdout, coreio.Envelope{Type: "log", Line: line})
	})
	if err != nil {
		return err
	}
	defer logger.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger.ClearSecrets()
	logger.Infof("==== 开始:%s ====", opTitle(req.Operation))
	d := deploy.New(logger, assets.InstallScript, req.UseSudo)
	result, err := dispatch(ctx, d, req)
	if err != nil {
		logger.Errorf("==== 失败:%s ====", opTitle(req.Operation))
		emit(stdout, coreio.Envelope{Type: "error", Message: err.Error()})
		return err
	}
	logger.Infof("==== 完成:%s ====", opTitle(req.Operation))
	emit(stdout, coreio.Envelope{Type: "done", Message: opTitle(req.Operation), Result: result})
	return nil
}

func validateRun(req coreio.RunRequest) error {
	if strings.TrimSpace(req.Profile.Host) == "" {
		return errors.New("主机不能为空")
	}
	if strings.TrimSpace(req.Profile.User) == "" {
		return errors.New("用户不能为空")
	}
	if req.Profile.Port <= 0 || req.Profile.Port > 65535 {
		return errors.New("端口必须是 1-65535 的整数")
	}
	switch req.Operation {
	case "test", "apt", "install", "update", "uninstall", "status", "detect-firewall", "allow-port", "disable-firewall":
	default:
		return fmt.Errorf("未知操作: %s", req.Operation)
	}
	if req.Operation == "allow-port" {
		if req.Port <= 0 || req.Port > 65535 {
			return errors.New("端口必须是 1-65535 的整数")
		}
		if !req.TCP && !req.UDP {
			return errors.New("至少选择一种协议(TCP / UDP)")
		}
	}
	return nil
}

func dispatch(ctx context.Context, d *deploy.Deployer, req coreio.RunRequest) (any, error) {
	switch req.Operation {
	case "test":
		return nil, d.TestConnection(ctx, req.Profile)
	case "apt":
		return nil, d.AptUpdate(ctx, req.Profile, req.AptUpgrade)
	case "install":
		return nil, d.Install(ctx, req.Profile, normalizeMirror(req.Mirror))
	case "update":
		return nil, d.Update(ctx, req.Profile, normalizeMirror(req.Mirror))
	case "uninstall":
		return nil, d.Uninstall(ctx, req.Profile)
	case "status":
		return nil, d.ServiceStatus(ctx, req.Profile)
	case "detect-firewall":
		info, err := d.DetectFirewall(ctx, req.Profile)
		return info, err
	case "allow-port":
		return nil, d.AllowPort(ctx, req.Profile, req.Port, req.TCP, req.UDP)
	case "disable-firewall":
		return nil, d.DisableFirewall(ctx, req.Profile)
	default:
		return nil, fmt.Errorf("未知操作: %s", req.Operation)
	}
}

func normalizeMirror(mirror string) string {
	mirror = strings.TrimSpace(mirror)
	if mirror == "" {
		return config.DefaultMirror
	}
	return mirror
}

func opTitle(op string) string {
	switch op {
	case "test":
		return "测试连接"
	case "apt":
		return "系统准备"
	case "install":
		return "安装管理器"
	case "update":
		return "升级管理器"
	case "uninstall":
		return "卸载管理器"
	case "status":
		return "服务状态"
	case "detect-firewall":
		return "检测防火墙"
	case "allow-port":
		return "放行端口"
	case "disable-firewall":
		return "关闭防火墙"
	default:
		return op
	}
}

func emit(w io.Writer, env coreio.Envelope) {
	data, err := json.Marshal(env)
	if err != nil {
		fmt.Fprintf(w, `{"type":"error","message":"编码响应失败: %s"}`+"\n", err)
		return
	}
	fmt.Fprintln(w, string(data))
}
