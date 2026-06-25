// Package deploy 把“在远端 Linux 上完成一项部署动作”编排成高层方法,
// 供 UI 直接调用。每个方法都接受 context(支持取消)并通过 logx.Logger 输出进度。
package deploy

import (
	"context"
	"fmt"
	"strings"
	"time"

	"dst-deployer/internal/config"
	"dst-deployer/internal/logx"
	"dst-deployer/internal/sshx"
)

// 远端临时脚本路径(每次执行前重新上传,保证与本程序内置版本一致)。
const remoteScriptPath = "/tmp/dst-install.sh"

// 连接超时。
const dialTimeout = 20 * time.Second

// Deployer 持有一次操作所需的全部上下文。
type Deployer struct {
	log     *logx.Logger
	script  []byte // 内置的 install-dst.sh 内容
	useSudo bool
}

// New 创建 Deployer。script 为内置安装脚本内容,useSudo 见 config.Config.UseSudo。
func New(log *logx.Logger, script []byte, useSudo bool) *Deployer {
	return &Deployer{log: log, script: script, useSudo: useSudo}
}

// connect 建立连接并把四元组登记为敏感值(后续日志自动遮挡)。
func (d *Deployer) connect(ctx context.Context, p config.Profile) (*sshx.Client, error) {
	d.log.Secret(p.Password, p.User, p.Host)
	d.log.Infof("连接 %s@%s:%d ...", logx.MaskUser(p.User), logx.MaskHost(p.Host), p.Port)
	cli, err := sshx.Dial(ctx, p.Host, p.Port, p.User, p.Password, dialTimeout)
	if err != nil {
		d.log.Errorf("连接失败: %v", err)
		return nil, err
	}
	d.log.Infof("连接成功(注意:未校验主机密钥,等同首次自动信任)")
	return cli, nil
}

// run 执行一条命令并把输出转发到日志。
func (d *Deployer) run(ctx context.Context, cli *sshx.Client, title, cmd string) error {
	d.log.Infof("▶ %s", title)
	err := cli.Run(ctx, cmd, d.useSudo, func(line string) { d.log.Raw(line) })
	if err != nil {
		d.log.Errorf("✗ %s 失败: %v", title, err)
		return err
	}
	d.log.Infof("✓ %s 完成", title)
	return nil
}

// TestConnection 仅验证四元组能否登录,并打印系统信息。
func (d *Deployer) TestConnection(ctx context.Context, p config.Profile) error {
	cli, err := d.connect(ctx, p)
	if err != nil {
		return err
	}
	defer cli.Close()
	return d.run(ctx, cli, "测试连接(读取系统信息)",
		`echo "主机: $(hostname)"; echo "系统: $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")"; echo "架构: $(uname -m)"; echo "当前用户: $(id -un)"`)
}

// AptUpdate 执行 apt 软件源更新;upgrade 为 true 时再执行升级。
// 非 Debian/Ubuntu 系统(无 apt-get)会给出友好提示。
func (d *Deployer) AptUpdate(ctx context.Context, p config.Profile, upgrade bool) error {
	cli, err := d.connect(ctx, p)
	if err != nil {
		return err
	}
	defer cli.Close()

	if err := d.run(ctx, cli, "检查 apt 可用性",
		`command -v apt-get >/dev/null 2>&1 || { echo "本系统无 apt-get(可能非 Debian/Ubuntu),跳过"; exit 0; }`); err != nil {
		return err
	}
	if err := d.run(ctx, cli, "apt-get update", `DEBIAN_FRONTEND=noninteractive apt-get update`); err != nil {
		return err
	}
	if upgrade {
		if err := d.run(ctx, cli, "apt-get upgrade",
			`DEBIAN_FRONTEND=noninteractive apt-get -y upgrade`); err != nil {
			return err
		}
	}
	// 确保 curl 存在(install-dst.sh 下载发布包需要)。
	return d.run(ctx, cli, "确保 curl 已安装",
		`command -v curl >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y curl`)
}

// uploadScript 把内置脚本上传到远端临时路径。
func (d *Deployer) uploadScript(cli *sshx.Client) error {
	d.log.Infof("上传安装脚本到 %s(%d 字节)", remoteScriptPath, len(d.script))
	if err := cli.Upload(d.script, remoteScriptPath, 0o755); err != nil {
		d.log.Errorf("上传脚本失败: %v", err)
		return err
	}
	return nil
}

// runScript 上传并以指定动作运行 install-dst.sh。
// mirror 为空则不追加 mirror 参数(脚本内部用其默认清华源)。
func (d *Deployer) runScript(ctx context.Context, p config.Profile, action, mirror string) error {
	cli, err := d.connect(ctx, p)
	if err != nil {
		return err
	}
	defer cli.Close()

	if err := d.uploadScript(cli); err != nil {
		return err
	}
	cmd := fmt.Sprintf("bash %s %s", shellQuote(remoteScriptPath), shellQuote(action))
	if mirror != "" {
		cmd += fmt.Sprintf(" mirror=%s", shellQuote(mirror))
	}
	return d.run(ctx, cli, fmt.Sprintf("执行 install-dst.sh %s", action), cmd)
}

func shellQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'"
}

// Install 安装管理器本体。
func (d *Deployer) Install(ctx context.Context, p config.Profile, mirror string) error {
	return d.runScript(ctx, p, "install", mirror)
}

// Update 升级管理器本体(保留游戏/存档/数据库)。
func (d *Deployer) Update(ctx context.Context, p config.Profile, mirror string) error {
	return d.runScript(ctx, p, "update", mirror)
}

// Uninstall 卸载管理器本体(保留游戏/缓存)。
func (d *Deployer) Uninstall(ctx context.Context, p config.Profile) error {
	return d.runScript(ctx, p, "uninstall", "")
}

// ServiceStatus 查询 systemd 服务状态。
func (d *Deployer) ServiceStatus(ctx context.Context, p config.Profile) error {
	cli, err := d.connect(ctx, p)
	if err != nil {
		return err
	}
	defer cli.Close()
	return d.run(ctx, cli, "查询服务状态",
		`systemctl status dst-serverd --no-pager 2>&1 | head -n 20 || echo "服务未安装"`)
}
