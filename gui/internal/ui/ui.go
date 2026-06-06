// Package ui 用 Fyne 构建主窗口,把连接表单、动作按钮与实时日志组合起来。
package ui

import (
	"context"
	"errors"
	"fmt"
	"image/color"
	"net/url"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"

	"dst-deployer/internal/config"
	"dst-deployer/internal/deploy"
	"dst-deployer/internal/logx"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/widget"
)

// 最多在界面保留的日志行数(超过则丢弃最旧的,避免界面卡顿)。
const maxLogLines = 1500

// 状态颜色。
var (
	colorIdle    = color.NRGBA{R: 0x75, G: 0x75, B: 0x75, A: 0xff} // 灰
	colorRunning = color.NRGBA{R: 0x15, G: 0x65, B: 0xc0, A: 0xff} // 蓝
	colorSuccess = color.NRGBA{R: 0x2e, G: 0x7d, B: 0x32, A: 0xff} // 绿
	colorFail    = color.NRGBA{R: 0xc6, G: 0x28, B: 0x28, A: 0xff} // 红
)

// 帮助文档地址(暂用占位域名,后续替换为正式文档)。
const helpURL = "https://example.com"

type appUI struct {
	app    fyne.App
	win    fyne.Window
	cfg    *config.Config
	log    *logx.Logger
	script []byte

	// 表单
	profileSelect *widget.Select
	nameEntry     *widget.Entry
	hostEntry     *widget.Entry
	portEntry     *widget.Entry
	userEntry     *widget.Entry
	passEntry     *widget.Entry
	mirrorEntry   *widget.Entry
	sudoCheck     *widget.Check
	upgradeCheck  *widget.Check

	// 日志与状态
	logText    *widget.RichText
	logSeg     *widget.TextSegment
	logScroll  *container.Scroll
	logLines   []string
	statusText *canvas.Text

	// 动作按钮(提升为字段,便于按阶段改变其状态/外观)
	testBtn   *widget.Button
	aptBtn    *widget.Button
	instBtn   *widget.Button
	updBtn    *widget.Button
	uninstBtn *widget.Button
	statusBtn *widget.Button

	// 开放端口页
	fwPortEntry   *widget.Entry
	fwProtoSelect *widget.Select
	fwDetectBtn   *widget.Button
	fwAllowBtn    *widget.Button
	fwDisableBtn  *widget.Button
	fwStatusText  *canvas.Text // 检测结果摘要
	fwKind        string       // 最近检测到的防火墙类型
	fwActive      bool         // 最近检测到的活动状态

	cancelButton *widget.Button

	mu        sync.Mutex
	running   bool
	cancel    context.CancelFunc
	installed bool   // 本会话内是否已成功安装(影响安装按钮可用性)
	lastHost  string // 最近一次操作的主机(用于成功提示里的访问网址)
}

// Build 组装并返回主窗口。
func Build(a fyne.App, cfg *config.Config, logger *logx.Logger, script []byte) fyne.Window {
	u := &appUI{
		app:    a,
		win:    a.NewWindow("DST 服务器部署工具"),
		cfg:    cfg,
		log:    logger,
		script: script,
	}
	u.buildForm()
	u.buildLog()

	// 日志回调:从工作协程经 fyne.Do 安全地刷到 UI。
	logger.SetSink(func(line string) {
		fyne.Do(func() {
			u.appendLog(line)
		})
	})

	tabs := container.NewAppTabs(
		container.NewTabItem("部署", u.deployTab()),
		container.NewTabItem("开放端口", u.firewallTab()),
		container.NewTabItem("设置", u.settingsTab()),
		container.NewTabItem("帮助", u.helpTab()),
	)
	tabs.SetTabLocation(container.TabLocationTop)

	content := container.NewBorder(nil, u.bottomBar(), nil, nil, tabs)
	u.win.SetContent(content)
	u.win.Resize(fyne.NewSize(760, 560))

	u.loadSelectedProfile()
	u.log.Infof("就绪。请选择或填写连接信息后开始操作。")
	return u.win
}

// ---------------------------------------------------------------- 表单构建

func (u *appUI) buildForm() {
	u.nameEntry = widget.NewEntry()
	u.nameEntry.SetPlaceHolder("配置名称,如:阿里云服务器-A")
	u.hostEntry = widget.NewEntry()
	u.hostEntry.SetPlaceHolder("主机 IP 或域名")
	u.portEntry = widget.NewEntry()
	u.portEntry.SetText("22")
	u.userEntry = widget.NewEntry()
	u.userEntry.SetPlaceHolder("登录用户,如:root")
	u.passEntry = widget.NewPasswordEntry()
	u.passEntry.SetPlaceHolder("登录密码")
	u.mirrorEntry = widget.NewEntry()
	u.mirrorEntry.SetText(u.cfg.Mirror)
	u.mirrorEntry.SetPlaceHolder(config.DefaultMirror)

	u.sudoCheck = widget.NewCheck("非 root 用户用 sudo 提权(用同一密码)", nil)
	u.sudoCheck.SetChecked(u.cfg.UseSudo)
	u.upgradeCheck = widget.NewCheck("系统准备时顺带 apt upgrade(较慢)", nil)
	u.upgradeCheck.SetChecked(u.cfg.AptUpgrade)

	u.profileSelect = widget.NewSelect(u.cfg.Names(), func(name string) {
		u.cfg.Selected = name
		if p, ok := u.cfg.Find(name); ok {
			u.fillForm(p)
		}
	})
	if u.cfg.Selected != "" {
		u.profileSelect.SetSelected(u.cfg.Selected)
	}
	u.profileSelect.PlaceHolder = "（选择已保存的连接）"
}

// newWrapLabel 创建一个自动换行的说明文字标签。
func newWrapLabel(text string) *widget.Label {
	l := widget.NewLabel(text)
	l.Wrapping = fyne.TextWrapWord
	return l
}

// labeledRow 把一个左侧标签和右侧控件拼成一行(控件占满剩余宽度)。
func labeledRow(label string, obj fyne.CanvasObject) fyne.CanvasObject {
	return container.NewBorder(nil, nil, widget.NewLabel(label), nil, obj)
}

// deployTab 是主操作页:连接信息 + 动作按钮 + 实时日志。布局紧凑,适配 1080p。
func (u *appUI) deployTab() fyne.CanvasObject {
	saveBtn := widget.NewButton("保存", u.onSaveProfile)
	delBtn := widget.NewButton("删除", u.onDeleteProfile)
	profileRow := container.NewBorder(nil, nil, widget.NewLabel("连接"),
		container.NewHBox(saveBtn, delBtn), u.profileSelect)

	conn := container.NewVBox(
		profileRow,
		container.NewGridWithColumns(2,
			labeledRow("主机", u.hostEntry),
			labeledRow("端口", u.portEntry),
		),
		container.NewGridWithColumns(2,
			labeledRow("用户", u.userEntry),
			labeledRow("密码", u.passEntry),
		),
		labeledRow("命名", u.nameEntry),
	)

	// 动作按钮(提升为字段,便于按部署阶段改变外观/可用性)。
	u.testBtn = widget.NewButton("① 测试连接", func() { u.runOp("测试连接", u.opTest) })
	u.aptBtn = widget.NewButton("② 系统准备", func() { u.runOp("系统准备", u.opApt) })
	u.statusBtn = widget.NewButton("查看服务状态", func() { u.runOp("服务状态", u.opStatus) })
	u.instBtn = widget.NewButton("③ 安装管理器", func() { u.runOp("安装管理器", u.opInstall) })
	u.updBtn = widget.NewButton("升级管理器", func() { u.runOp("升级管理器", u.opUpdate) })
	u.uninstBtn = widget.NewButton("卸载管理器", func() {
		u.confirm("确认卸载", "将删除管理器源码与服务(保留游戏存档与数据库)。确定继续?", func() {
			u.runOp("卸载管理器", u.opUninstall)
		})
	})
	// 视觉权重:安装是主操作(高亮蓝),卸载是危险操作(红)。
	u.instBtn.Importance = widget.HighImportance
	u.uninstBtn.Importance = widget.DangerImportance

	u.cancelButton = widget.NewButton("取消", u.onCancel)
	u.cancelButton.Disable()
	clearBtn := widget.NewButton("清空日志", u.clearLog)
	openLogBtn := widget.NewButton("日志目录", u.onOpenLogDir)

	grid := container.NewGridWithColumns(3,
		u.testBtn, u.aptBtn, u.statusBtn,
		u.instBtn, u.updBtn, u.uninstBtn)

	header := container.NewVBox(
		conn,
		widget.NewSeparator(),
		grid,
	)
	logTools := container.NewHBox(u.cancelButton, clearBtn, openLogBtn)
	logArea := container.NewBorder(
		widget.NewLabel("运行日志(已自动遮挡主机/用户/密码):"),
		logTools, nil, nil, u.logScroll)

	u.applyButtonState() // 初始按钮可用性
	return container.NewBorder(header, nil, nil, nil, logArea)
}

// firewallTab 处理【系统防火墙】:检测类型/状态、放行端口(TCP/UDP)、关闭防火墙。
func (u *appUI) firewallTab() fyne.CanvasObject {
	// 醒目提示:系统防火墙 ≠ 云安全组。
	notice := canvas.NewText("⚠ 这里操作的是服务器“系统防火墙”,不是云服务商的“安全组”!", colorFail)
	notice.TextSize = 13
	notice.TextStyle = fyne.TextStyle{Bold: true}
	explain := newWrapLabel(
		"二者相互独立,都要放行端口外网才连得上:\n" +
			"• 系统防火墙:服务器系统里的 ufw / firewalld / iptables 等 —— 本页可以处理;\n" +
			"• 云安全组:阿里云/腾讯云/AWS 等控制台里的入站规则 —— 必须你自己去云控制台放行,本工具无能为力。\n" +
			"管理面板用 8000/TCP;饥荒游戏每个房间还会占用一段 UDP 端口(默认从 10999 起),也需放行。")

	u.fwStatusText = canvas.NewText("尚未检测,请先点【检测防火墙】", colorIdle)
	u.fwStatusText.TextSize = 13
	u.fwStatusText.TextStyle = fyne.TextStyle{Bold: true}

	u.fwDetectBtn = widget.NewButton("① 检测防火墙", func() { u.runOp("检测防火墙", u.opDetectFirewall) })
	u.fwDetectBtn.Importance = widget.HighImportance

	u.fwPortEntry = widget.NewEntry()
	u.fwPortEntry.SetText("8000")
	u.fwProtoSelect = widget.NewSelect(
		[]string{"TCP + UDP(推荐)", "仅 TCP", "仅 UDP"}, nil)
	u.fwProtoSelect.SetSelectedIndex(0)

	u.fwAllowBtn = widget.NewButton("② 放行此端口", func() {
		port, err := u.parsePort(u.fwPortEntry.Text)
		if err != nil {
			u.showError(err)
			return
		}
		u.runOp(fmt.Sprintf("放行端口 %d", port), u.opAllowPort)
	})
	u.fwAllowBtn.Importance = widget.HighImportance

	u.fwDisableBtn = widget.NewButton("关闭系统防火墙", func() {
		u.confirm("确认关闭系统防火墙",
			"关闭后服务器将不再有系统层防护,所有端口对外开放(仍受云安全组限制)。\n"+
				"仅在你清楚风险、或云安全组已严格配置时使用。确定关闭?", func() {
				u.runOp("关闭防火墙", u.opDisableFirewall)
			})
	})
	u.fwDisableBtn.Importance = widget.DangerImportance

	portRow := container.NewBorder(nil, nil, widget.NewLabel("端口"),
		container.NewHBox(widget.NewLabel("协议"), u.fwProtoSelect), u.fwPortEntry)

	return container.NewVBox(
		notice,
		explain,
		widget.NewSeparator(),
		u.fwDetectBtn,
		container.NewPadded(u.fwStatusText),
		widget.NewSeparator(),
		widget.NewLabel("放行端口(防火墙开着时用):"),
		portRow,
		u.fwAllowBtn,
		widget.NewSeparator(),
		widget.NewLabel("或者,直接关闭系统防火墙(不推荐):"),
		u.fwDisableBtn,
	)
}

// settingsTab 收纳不常改的选项,避免主页过长。
func (u *appUI) settingsTab() fyne.CanvasObject {
	return container.NewVBox(
		labeledRow("PyPI 镜像", u.mirrorEntry),
		newWrapLabel("留空则用默认清华源;默认不使用官方 pypi.org(国内不可达)。"),
		widget.NewSeparator(),
		u.sudoCheck,
		newWrapLabel("登录用户不是 root 时,用同一密码通过 sudo 提权执行安装命令。"),
		u.upgradeCheck,
		newWrapLabel("勾选后“系统准备”会顺带升级所有系统软件包,耗时较长。"),
	)
}

// helpTab 给新手的说明与操作步骤。
func (u *appUI) helpTab() fyne.CanvasObject {
	title := widget.NewLabelWithStyle("饥荒(DST)服务器一键部署助手",
		fyne.TextAlignLeading, fyne.TextStyle{Bold: true})
	intro := newWrapLabel(
		"本工具帮你把「饥荒服务器管理器」安装到一台远程 Linux 服务器上,全程不用懂 Linux。\n" +
			"你只需要准备好服务器的 4 项登录信息:主机地址、SSH 端口(通常是 22)、登录用户(通常是 root)、登录密码。")
	steps := newWrapLabel(
		"操作步骤(都在「部署」页):\n" +
			"① 填写 4 项连接信息,点【保存】记住它;\n" +
			"② 点【测试连接】,日志显示“完成”说明能连上;\n" +
			"③ 点【系统准备】更新系统并安装必要工具;\n" +
			"④ 点【安装】开始部署,完成后日志会给出访问网址(形如 http://服务器IP:8000/);\n" +
			"⑤ 以后要更新点【升级】,不想要了点【卸载】(会保留存档与数据库)。")
	link := newHelpLink("📖 在线帮助 / 遇到问题点这里")
	return container.NewVScroll(container.NewVBox(title, intro, steps, widget.NewSeparator(), link))
}

// newHelpLink 构造帮助超链接(URL 解析失败则退化为无跳转链接)。
func newHelpLink(text string) *widget.Hyperlink {
	if parsed, err := url.Parse(helpURL); err == nil {
		return widget.NewHyperlink(text, parsed)
	}
	return widget.NewHyperlink(text, nil)
}

// bottomBar 是窗口底部常驻栏:左侧彩色状态文字,右侧帮助链接。
func (u *appUI) bottomBar() fyne.CanvasObject {
	return container.NewBorder(widget.NewSeparator(), nil,
		container.NewPadded(u.statusText),
		newHelpLink("📖 使用帮助"), layout.NewSpacer())
}

func (u *appUI) buildLog() {
	// 用 RichText 展示日志:正常前景色(不会像禁用 Entry 那样灰显发浅),
	// 外套 VScroll,每次追加后滚动到底,实现 tail -f 跟踪效果。
	u.logSeg = &widget.TextSegment{
		Text:  "",
		Style: widget.RichTextStyle{TextStyle: fyne.TextStyle{Monospace: true}},
	}
	u.logText = widget.NewRichText(u.logSeg)
	u.logText.Wrapping = fyne.TextWrapWord
	u.logScroll = container.NewVScroll(u.logText)

	u.statusText = canvas.NewText("● 空闲", colorIdle)
	u.statusText.TextSize = 14
	u.statusText.TextStyle = fyne.TextStyle{Bold: true}
}

// appendLog 追加一行日志并滚动到底部(tail -f 效果)。
func (u *appUI) appendLog(line string) {
	u.logLines = append(u.logLines, line)
	if len(u.logLines) > maxLogLines {
		u.logLines = u.logLines[len(u.logLines)-maxLogLines:]
	}
	u.logSeg.Text = strings.Join(u.logLines, "\n")
	u.logText.Refresh()
	u.logScroll.ScrollToBottom()
}

// clearLog 清空日志显示。
func (u *appUI) clearLog() {
	u.logLines = nil
	u.logSeg.Text = ""
	u.logText.Refresh()
	u.logScroll.ScrollToBottom()
}

// setStatus 设置底部状态栏文字与颜色。
func (u *appUI) setStatus(c color.Color, msg string) {
	u.statusText.Text = msg
	u.statusText.Color = c
	u.statusText.Refresh()
}

// ---------------------------------------------------------------- 表单数据

func (u *appUI) fillForm(p config.Profile) {
	u.nameEntry.SetText(p.Name)
	u.hostEntry.SetText(p.Host)
	if p.Port > 0 {
		u.portEntry.SetText(strconv.Itoa(p.Port))
	}
	u.userEntry.SetText(p.User)
	u.passEntry.SetText(p.Password)
}

func (u *appUI) loadSelectedProfile() {
	if p, ok := u.cfg.Find(u.cfg.Selected); ok {
		u.fillForm(p)
	}
}

// formProfile 从表单读取并校验四元组。
func (u *appUI) formProfile() (config.Profile, error) {
	host := strings.TrimSpace(u.hostEntry.Text)
	user := strings.TrimSpace(u.userEntry.Text)
	if host == "" {
		return config.Profile{}, errors.New("主机不能为空")
	}
	if user == "" {
		return config.Profile{}, errors.New("用户不能为空")
	}
	port, err := strconv.Atoi(strings.TrimSpace(u.portEntry.Text))
	if err != nil || port <= 0 || port > 65535 {
		return config.Profile{}, errors.New("端口必须是 1-65535 的整数")
	}
	name := strings.TrimSpace(u.nameEntry.Text)
	if name == "" {
		name = fmt.Sprintf("%s@%s", user, host)
	}
	return config.Profile{
		Name:     name,
		Host:     host,
		Port:     port,
		User:     user,
		Password: u.passEntry.Text,
	}, nil
}

func (u *appUI) onSaveProfile() {
	p, err := u.formProfile()
	if err != nil {
		u.showError(err)
		return
	}
	u.cfg.Upsert(p)
	u.cfg.Selected = p.Name
	u.persist()
	u.profileSelect.Options = u.cfg.Names()
	u.profileSelect.Refresh()
	u.profileSelect.SetSelected(p.Name)
	u.log.Infof("已保存连接:%s", p.Name)
}

func (u *appUI) onDeleteProfile() {
	name := strings.TrimSpace(u.nameEntry.Text)
	if name == "" {
		return
	}
	u.confirm("确认删除", fmt.Sprintf("删除已保存连接「%s」?", name), func() {
		u.cfg.Delete(name)
		if u.cfg.Selected == name {
			u.cfg.Selected = ""
		}
		u.persist()
		u.profileSelect.Options = u.cfg.Names()
		u.profileSelect.Refresh()
		u.profileSelect.ClearSelected()
		u.log.Infof("已删除连接:%s", name)
	})
}

// persist 把当前偏好(镜像/勾选项)与 profiles 一并落盘。
func (u *appUI) persist() {
	u.cfg.Mirror = strings.TrimSpace(u.mirrorEntry.Text)
	if u.cfg.Mirror == "" {
		u.cfg.Mirror = config.DefaultMirror
	}
	u.cfg.UseSudo = u.sudoCheck.Checked
	u.cfg.AptUpgrade = u.upgradeCheck.Checked
	if err := u.cfg.Save(); err != nil {
		u.log.Errorf("保存配置失败: %v", err)
		u.showError(err)
	}
}

// ---------------------------------------------------------------- 操作编排

type opFunc func(ctx context.Context, d *deploy.Deployer, p config.Profile, mirror string) error

func (u *appUI) runOp(name string, fn opFunc) {
	u.mu.Lock()
	if u.running {
		u.mu.Unlock()
		u.log.Warnf("已有操作在进行,请先等待或取消")
		return
	}
	p, err := u.formProfile()
	if err != nil {
		u.mu.Unlock()
		u.showError(err)
		return
	}
	u.persist() // 每次操作前把偏好与(若有名字)连接存好
	mirror := u.cfg.Mirror
	d := deploy.New(u.log, u.script, u.sudoCheck.Checked)

	ctx, cancel := context.WithCancel(context.Background())
	u.running = true
	u.cancel = cancel
	u.lastHost = p.Host
	u.mu.Unlock()

	u.setBusy(true, name)
	u.log.ClearSecrets()
	u.log.Infof("==== 开始:%s ====", name)

	go func() {
		err := fn(ctx, d, p, mirror)
		cancel()
		fyne.Do(func() {
			u.mu.Lock()
			u.running = false
			u.cancel = nil
			u.mu.Unlock()
			if err != nil {
				u.log.Errorf("==== 失败:%s ====", name)
				u.setStatus(colorFail, "✘ "+name+"失败 —— 详情见下方日志")
			} else {
				u.log.Infof("==== 完成:%s ====", name)
				u.onOpSuccess(name)
			}
			u.setBusy(false, name)
		})
	}()
}

func (u *appUI) onCancel() {
	u.mu.Lock()
	c := u.cancel
	u.mu.Unlock()
	if c != nil {
		u.log.Warnf("正在取消当前操作 ...")
		c()
	}
}

// onOpSuccess 在某动作成功后更新状态文字与按钮外观,给小白清晰反馈。
func (u *appUI) onOpSuccess(name string) {
	// 放行端口的动作名带端口号,前缀匹配。
	if strings.HasPrefix(name, "放行端口") {
		u.setStatus(colorSuccess, "✔ 系统防火墙已放行!切记:还要去云服务商【安全组】放行同一端口(TCP/UDP),外网才连得上。")
		return
	}
	switch name {
	case "检测防火墙":
		u.updateFwStatusText()
		u.setStatus(colorSuccess, "✔ 防火墙检测完成(详情见下方日志)")
	case "关闭防火墙":
		u.fwActive = false
		u.updateFwStatusText()
		u.setStatus(colorSuccess, "✔ 系统防火墙已关闭(请注意安全;外网访问仍受云安全组限制)")
	case "测试连接":
		u.setStatus(colorSuccess, "✔ 连接成功,可以开始部署(下一步:系统准备)")
	case "系统准备":
		u.setStatus(colorSuccess, "✔ 系统已更新、环境就绪(下一步:安装管理器)")
		u.aptBtn.SetText("✔ 系统已准备")
	case "安装管理器", "升级管理器":
		u.installed = true
		u.instBtn.SetText("✔ 已安装")
		u.instBtn.Importance = widget.MediumImportance
		u.updBtn.Importance = widget.HighImportance // 后续主操作变成“升级”
		verb := "安装"
		if name == "升级管理器" {
			verb = "升级"
		}
		u.setStatus(colorSuccess, fmt.Sprintf("✔ DST 管理器%s完成!浏览器打开 http://%s:8000/", verb, u.lastHost))
	case "卸载管理器":
		u.installed = false
		u.instBtn.SetText("③ 安装管理器")
		u.instBtn.Importance = widget.HighImportance
		u.updBtn.Importance = widget.MediumImportance
		u.setStatus(colorSuccess, "✔ 已卸载(游戏存档与数据库已保留)")
	case "服务状态":
		u.setStatus(colorSuccess, "✔ 已获取服务状态(见下方日志)")
	default:
		u.setStatus(colorSuccess, "✔ "+name+"完成")
	}
}

// applyButtonState 根据当前阶段设置各按钮可用性(供 setBusy 收尾时调用)。
func (u *appUI) applyButtonState() {
	u.testBtn.Enable()
	u.aptBtn.Enable()
	u.statusBtn.Enable()
	u.updBtn.Enable()
	u.uninstBtn.Enable()
	// 已安装则禁用“安装”按钮,引导用户改用“升级”。
	if u.installed {
		u.instBtn.Disable()
	} else {
		u.instBtn.Enable()
	}
	u.instBtn.Refresh()
	u.updBtn.Refresh()
	// 开放端口页按钮(可能在本方法首次调用时尚未创建,需判空)。
	u.enableFwButtons(true)
}

func (u *appUI) setBusy(busy bool, name string) {
	if busy {
		u.testBtn.Disable()
		u.aptBtn.Disable()
		u.statusBtn.Disable()
		u.instBtn.Disable()
		u.updBtn.Disable()
		u.uninstBtn.Disable()
		u.enableFwButtons(false)
		u.cancelButton.Enable()
		u.setStatus(colorRunning, "⏳ 正在执行:"+name+" …")
	} else {
		u.cancelButton.Disable()
		u.applyButtonState()
	}
}

// enableFwButtons 统一启用/禁用“开放端口”页的按钮(判空以兼容尚未构建时)。
func (u *appUI) enableFwButtons(enable bool) {
	for _, b := range []*widget.Button{u.fwDetectBtn, u.fwAllowBtn, u.fwDisableBtn} {
		if b == nil {
			continue
		}
		if enable {
			b.Enable()
		} else {
			b.Disable()
		}
	}
}

// --- 各动作绑定到 deploy 包 ---

func (u *appUI) opTest(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	return d.TestConnection(ctx, p)
}
func (u *appUI) opApt(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	return d.AptUpdate(ctx, p, u.upgradeCheck.Checked)
}
func (u *appUI) opInstall(ctx context.Context, d *deploy.Deployer, p config.Profile, mirror string) error {
	return d.Install(ctx, p, mirror)
}
func (u *appUI) opUpdate(ctx context.Context, d *deploy.Deployer, p config.Profile, mirror string) error {
	return d.Update(ctx, p, mirror)
}
func (u *appUI) opUninstall(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	return d.Uninstall(ctx, p)
}
func (u *appUI) opStatus(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	return d.ServiceStatus(ctx, p)
}
func (u *appUI) opDetectFirewall(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	info, err := d.DetectFirewall(ctx, p)
	if err != nil {
		return err
	}
	u.fwKind = info.Kind
	u.fwActive = info.Active
	return nil
}
func (u *appUI) opAllowPort(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	port, err := u.parsePort(u.fwPortEntry.Text)
	if err != nil {
		return err
	}
	tcp, udp := u.protoFlags()
	return d.AllowPort(ctx, p, port, tcp, udp)
}
func (u *appUI) opDisableFirewall(ctx context.Context, d *deploy.Deployer, p config.Profile, _ string) error {
	return d.DisableFirewall(ctx, p)
}

// parsePort 校验端口输入。
func (u *appUI) parsePort(s string) (int, error) {
	port, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil || port <= 0 || port > 65535 {
		return 0, errors.New("端口必须是 1-65535 的整数")
	}
	return port, nil
}

// protoFlags 把协议下拉选项翻译成 tcp/udp 布尔。
func (u *appUI) protoFlags() (tcp, udp bool) {
	switch u.fwProtoSelect.SelectedIndex() {
	case 1:
		return true, false
	case 2:
		return false, true
	default:
		return true, true
	}
}

// updateFwStatusText 依据最近检测结果刷新“开放端口”页的状态摘要。
func (u *appUI) updateFwStatusText() {
	if u.fwStatusText == nil {
		return
	}
	var c color.Color
	var msg string
	switch u.fwKind {
	case "none", "":
		c, msg = colorSuccess, "✔ 未检测到系统防火墙 —— 系统层无需放行;请确认云【安全组】已放行端口。"
	default:
		if u.fwActive {
			c = color.NRGBA{R: 0xe6, G: 0x51, B: 0x00, A: 0xff} // 橙:需要处理
			msg = fmt.Sprintf("● 系统防火墙:%s(已启用)。请在下方放行端口,或关闭防火墙,外网才能连入。", u.fwKind)
		} else {
			c = colorSuccess
			msg = fmt.Sprintf("✔ 系统防火墙:%s(未启用)—— 系统层默认放行;重点检查云【安全组】。", u.fwKind)
		}
	}
	u.fwStatusText.Text = msg
	u.fwStatusText.Color = c
	u.fwStatusText.Refresh()
}

// ---------------------------------------------------------------- 杂项

// 以下三个对话框用 NewCustom*/自带内容构造,不带 Fyne 默认大图标,
// 避免“图标过大、与文字不匹配、布局错乱”的问题。

func (u *appUI) confirm(title, msg string, onYes func()) {
	content := newWrapLabel(msg)
	dialog.NewCustomConfirm(title, "确定", "取消", content, func(ok bool) {
		if ok {
			onYes()
		}
	}, u.win).Show()
}

func (u *appUI) showError(err error) {
	dialog.NewCustom("出错了", "知道了", newWrapLabel(err.Error()), u.win).Show()
}

func (u *appUI) showInfo(title, msg string) {
	dialog.NewCustom(title, "知道了", newWrapLabel(msg), u.win).Show()
}

func (u *appUI) onOpenLogDir() {
	dir, err := config.Dir()
	if err != nil {
		u.showError(err)
		return
	}
	logDir := filepath.Join(dir, "logs")
	if err := openPath(logDir); err != nil {
		// 打开失败就把路径展示出来,方便用户手动定位。
		u.showInfo("日志目录", logDir)
	}
}

// openPath 用系统默认方式打开文件夹。
func openPath(path string) error {
	switch runtime.GOOS {
	case "windows":
		return exec.Command("explorer", path).Start()
	case "darwin":
		return exec.Command("open", path).Start()
	default:
		return exec.Command("xdg-open", path).Start()
	}
}
