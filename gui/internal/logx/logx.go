// Package logx 提供带“隐私遮挡”的日志器:
//   - 同时写入按日期分割的日志文件,并回调给 UI 实时展示。
//   - 任何注册为“敏感值”的字符串(密码、用户名、主机)在写出前都会被替换,
//     避免四元组关键信息泄漏到日志文件或界面。
package logx

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// ansiRe 匹配 ANSI 转义序列(颜色/光标等 CSI、OSC)。
// 远端脚本(如 install-dst.sh)输出的颜色码在 GUI 里无法渲染,需先剥除。
var ansiRe = regexp.MustCompile(`\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]`)

// stripANSI 去掉字符串中的 ANSI 转义序列。
func stripANSI(s string) string {
	return ansiRe.ReplaceAllString(s, "")
}

// Sink 是 UI 侧的行回调;每产生一行日志(已遮挡)就调用一次。
type Sink func(line string)

// Logger 是线程安全的遮挡日志器。
type Logger struct {
	mu      sync.Mutex
	file    *os.File
	sink    Sink
	secrets []string // 待遮挡的敏感原文(按长度降序,先长后短避免子串残留)
}

// New 创建日志器:在 baseDir/logs 下按天写文件,并把每行转发给 sink。
// sink 可为 nil(仅写文件)。
func New(baseDir string, sink Sink) (*Logger, error) {
	logDir := filepath.Join(baseDir, "logs")
	if err := os.MkdirAll(logDir, 0o700); err != nil {
		return nil, fmt.Errorf("创建日志目录失败: %w", err)
	}
	name := fmt.Sprintf("deploy-%s.log", time.Now().Format("2006-01-02"))
	f, err := os.OpenFile(filepath.Join(logDir, name), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, fmt.Errorf("打开日志文件失败: %w", err)
	}
	return &Logger{file: f, sink: sink}, nil
}

// SetSink 替换 UI 回调(UI 构建完成后挂接)。
func (l *Logger) SetSink(s Sink) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.sink = s
}

// Secret 注册一个需要遮挡的敏感原文。空串忽略。
// 同一值重复注册无副作用。
func (l *Logger) Secret(values ...string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	for _, v := range values {
		if v == "" {
			continue
		}
		exists := false
		for _, s := range l.secrets {
			if s == v {
				exists = true
				break
			}
		}
		if !exists {
			l.secrets = append(l.secrets, v)
		}
	}
	// 长的在前,避免“短值是长值子串”时只遮住一部分。
	sortByLenDesc(l.secrets)
}

// ClearSecrets 清空敏感值登记(切换连接时调用)。
func (l *Logger) ClearSecrets() {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.secrets = nil
}

// Redact 返回把所有已登记敏感值替换为 *** 后的字符串。
func (l *Logger) Redact(s string) string {
	for _, secret := range l.secrets {
		if secret != "" {
			s = strings.ReplaceAll(s, secret, "******")
		}
	}
	return s
}

// Close 关闭底层日志文件。
func (l *Logger) Close() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.file != nil {
		return l.file.Close()
	}
	return nil
}

// 内部:写一行(已是最终文本,未遮挡),统一遮挡 + 加时间戳 + 落盘 + 回调。
func (l *Logger) emit(level, text string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	redacted := stripANSI(text) // 先剥除远端输出里的 ANSI 颜色码,避免界面/文件乱码
	for _, secret := range l.secrets {
		if secret != "" {
			redacted = strings.ReplaceAll(redacted, secret, "******")
		}
	}
	stamp := time.Now().Format("15:04:05")
	fileLine := fmt.Sprintf("%s %s %s", time.Now().Format("2006-01-02 15:04:05"), level, redacted)
	uiLine := fmt.Sprintf("%s %s", stamp, redacted)
	if l.file != nil {
		fmt.Fprintln(l.file, fileLine)
	}
	if l.sink != nil {
		l.sink(uiLine)
	}
}

// Infof 记录普通信息。
func (l *Logger) Infof(format string, a ...any) { l.emit("INFO ", fmt.Sprintf(format, a...)) }

// Warnf 记录警告。
func (l *Logger) Warnf(format string, a ...any) { l.emit("WARN ", fmt.Sprintf(format, a...)) }

// Errorf 记录错误。
func (l *Logger) Errorf(format string, a ...any) { l.emit("ERROR", fmt.Sprintf(format, a...)) }

// Raw 记录来自远端命令的原始输出行(已经过遮挡)。
func (l *Logger) Raw(line string) { l.emit("OUT  ", line) }

func sortByLenDesc(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && len(s[j]) > len(s[j-1]); j-- {
			s[j], s[j-1] = s[j-1], s[j]
		}
	}
}

// MaskHost 把主机地址做展示用遮挡:IPv4 仅保留首段,域名保留首字符。
// 例:192.168.1.50 -> 192.*.*.* ;example.com -> e****e.com 风格的近似。
func MaskHost(host string) string {
	if host == "" {
		return "(空)"
	}
	// IPv4
	if parts := strings.Split(host, "."); len(parts) == 4 && isAllNumeric(parts) {
		return parts[0] + ".*.*.*"
	}
	// 域名 / 其它:保留首尾字符
	if len(host) <= 2 {
		return "**"
	}
	return string(host[0]) + strings.Repeat("*", len(host)-2) + string(host[len(host)-1])
}

// MaskUser 遮挡用户名:保留首字符。
func MaskUser(user string) string {
	if user == "" {
		return "(空)"
	}
	if len(user) == 1 {
		return "*"
	}
	return string(user[0]) + strings.Repeat("*", len(user)-1)
}

func isAllNumeric(parts []string) bool {
	for _, p := range parts {
		if p == "" {
			return false
		}
		for _, c := range p {
			if c < '0' || c > '9' {
				return false
			}
		}
	}
	return true
}
