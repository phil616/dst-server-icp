// Package sshx 封装 SSH 连接、命令流式执行与文件上传。
//
// 设计要点:
//   - 密码认证(面向不熟悉密钥的用户)。
//   - Run 把远端 stdout/stderr 合并后按行实时回调,便于 UI 展示进度。
//   - 支持以 sudo -S 提权(把密码写入 stdin,不出现在命令行/进程列表)。
//   - 文件上传走 SFTP。
package sshx

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/pkg/sftp"
	"golang.org/x/crypto/ssh"
)

// Client 是一个已建立的 SSH 会话连接。
type Client struct {
	conn     *ssh.Client
	user     string
	password string
}

// LineFunc 是命令输出的逐行回调。
type LineFunc func(line string)

// Dial 用密码认证建立连接。timeout 为 TCP+握手超时。
//
// 安全说明:为降低非技术用户的使用门槛,这里采用 InsecureIgnoreHostKey,
// 即不校验主机密钥(等价于首次连接自动信任)。调用方应在日志中提示该风险。
func Dial(ctx context.Context, host string, port int, user, password string, timeout time.Duration) (*Client, error) {
	cfg := &ssh.ClientConfig{
		User:            user,
		Auth:            []ssh.AuthMethod{ssh.Password(password)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         timeout,
	}
	addr := net.JoinHostPort(host, fmt.Sprintf("%d", port))

	// 用 context 控制拨号超时/取消。
	d := net.Dialer{Timeout: timeout}
	netConn, err := d.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, fmt.Errorf("TCP 连接失败: %w", err)
	}
	sshConn, chans, reqs, err := ssh.NewClientConn(netConn, addr, cfg)
	if err != nil {
		netConn.Close()
		return nil, fmt.Errorf("SSH 握手/认证失败: %w", err)
	}
	return &Client{conn: ssh.NewClient(sshConn, chans, reqs), user: user, password: password}, nil
}

// Close 关闭连接。
func (c *Client) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// Run 在远端执行命令,合并 stdout/stderr 并逐行回调 onLine。
//
// useSudo 为 true 且登录用户非 root 时,命令会被包装为 `sudo -S -p '' bash -lc '<cmd>'`,
// 并把登录密码写入 stdin 供 sudo 读取(避免密码出现在命令行)。
// ctx 取消会尝试中断会话。返回命令退出码错误(非 0 退出返回 error)。
func (c *Client) Run(ctx context.Context, cmd string, useSudo bool, onLine LineFunc) error {
	sess, err := c.conn.NewSession()
	if err != nil {
		return fmt.Errorf("创建会话失败: %w", err)
	}
	defer sess.Close()

	full := cmd
	needSudoPass := false
	if useSudo && c.user != "root" {
		// 用 bash -lc 包裹原命令,保证 PATH/环境完整;sudo -S 从 stdin 读密码。
		full = fmt.Sprintf("sudo -S -p '' bash -lc %s", shellQuote(cmd))
		needSudoPass = true
	}

	stdin, err := sess.StdinPipe()
	if err != nil {
		return fmt.Errorf("获取 stdin 失败: %w", err)
	}
	stdout, err := sess.StdoutPipe()
	if err != nil {
		return fmt.Errorf("获取 stdout 失败: %w", err)
	}
	stderr, err := sess.StderrPipe()
	if err != nil {
		return fmt.Errorf("获取 stderr 失败: %w", err)
	}

	if err := sess.Start(full); err != nil {
		return fmt.Errorf("启动命令失败: %w", err)
	}

	// 先喂 sudo 密码,再关闭 stdin。
	if needSudoPass {
		io.WriteString(stdin, c.password+"\n")
	}
	stdin.Close()

	// 合并读取两路输出。
	var wg sync.WaitGroup
	scan := func(r io.Reader) {
		defer wg.Done()
		sc := bufio.NewScanner(r)
		sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
		for sc.Scan() {
			if onLine != nil {
				onLine(sc.Text())
			}
		}
	}
	wg.Add(2)
	go scan(stdout)
	go scan(stderr)

	// 监听 ctx 取消:发信号中断远端进程。
	done := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			sess.Signal(ssh.SIGTERM)
			sess.Close()
		case <-done:
		}
	}()

	waitErr := sess.Wait()
	close(done)
	wg.Wait()

	if ctx.Err() != nil {
		return fmt.Errorf("已取消: %w", ctx.Err())
	}
	if waitErr != nil {
		return fmt.Errorf("命令以非 0 退出: %w", waitErr)
	}
	return nil
}

// Upload 通过 SFTP 把内容写到远端路径,并设置权限。
func (c *Client) Upload(data []byte, remotePath string, mode uint32) error {
	sc, err := sftp.NewClient(c.conn)
	if err != nil {
		return fmt.Errorf("建立 SFTP 失败: %w", err)
	}
	defer sc.Close()

	f, err := sc.Create(remotePath)
	if err != nil {
		return fmt.Errorf("创建远端文件失败 %s: %w", remotePath, err)
	}
	if _, err := f.Write(data); err != nil {
		f.Close()
		return fmt.Errorf("写入远端文件失败: %w", err)
	}
	if err := f.Close(); err != nil {
		return fmt.Errorf("关闭远端文件失败: %w", err)
	}
	if err := sc.Chmod(remotePath, os.FileMode(mode)); err != nil {
		return fmt.Errorf("设置远端文件权限失败: %w", err)
	}
	return nil
}

// shellQuote 把字符串安全地包进单引号,供 bash -lc '<...>' 使用。
func shellQuote(s string) string {
	return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'"
}
