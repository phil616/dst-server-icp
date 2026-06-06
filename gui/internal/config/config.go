// Package config 负责把连接信息与偏好持久化为 JSON 文件,方便用户手动编辑。
//
// 文件位置:<用户配置目录>/dst-deployer/config.json
//   - Windows: %AppData%\dst-deployer\config.json
//   - Linux:   ~/.config/dst-deployer/config.json
//
// 注意:Profile.Password 以明文存储,以满足“方便手动配置”的诉求。
// 该文件应视为敏感文件(本程序写入时设为 0600 权限)。
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// 默认 PyPI 镜像,与 install-dst.sh 保持一致(默认不使用官方 pypi.org)。
const DefaultMirror = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"

// Profile 是一组 SSH 连接四元组。
type Profile struct {
	Name     string `json:"name"`     // 显示名(下拉框用)
	Host     string `json:"host"`     // 主机 IP 或域名
	Port     int    `json:"port"`     // SSH 端口
	User     string `json:"user"`     // 登录用户
	Password string `json:"password"` // 登录密码(明文,敏感)
}

// Config 是整个程序的持久化状态。
type Config struct {
	Profiles []Profile `json:"profiles"`
	Selected string    `json:"selected"` // 当前选中的 Profile.Name
	Mirror   string    `json:"mirror"`   // PyPI 镜像,空则用 DefaultMirror
	UseSudo  bool      `json:"use_sudo"` // 非 root 登录时,命令是否以 sudo -S 提权
	AptUpgrade bool    `json:"apt_upgrade"` // “系统准备”是否在 update 之后执行 upgrade
}

// Path 返回配置文件的绝对路径,并确保其父目录存在。
func Path() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", fmt.Errorf("无法定位用户配置目录: %w", err)
	}
	appDir := filepath.Join(dir, "dst-deployer")
	if err := os.MkdirAll(appDir, 0o700); err != nil {
		return "", fmt.Errorf("创建配置目录失败: %w", err)
	}
	return filepath.Join(appDir, "config.json"), nil
}

// Dir 返回程序专用目录(配置/日志的父目录)。
func Dir() (string, error) {
	p, err := Path()
	if err != nil {
		return "", err
	}
	return filepath.Dir(p), nil
}

// Default 返回带合理默认值的空配置。
func Default() *Config {
	return &Config{
		Profiles:   []Profile{},
		Mirror:     DefaultMirror,
		UseSudo:    true,
		AptUpgrade: false,
	}
}

// Load 读取配置;文件不存在时返回默认配置(不报错)。
func Load() (*Config, error) {
	p, err := Path()
	if err != nil {
		return nil, err
	}
	data, err := os.ReadFile(p)
	if os.IsNotExist(err) {
		return Default(), nil
	}
	if err != nil {
		return nil, fmt.Errorf("读取配置失败: %w", err)
	}
	cfg := Default()
	if err := json.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("解析配置失败(文件可能损坏): %w", err)
	}
	if cfg.Mirror == "" {
		cfg.Mirror = DefaultMirror
	}
	return cfg, nil
}

// Save 以 0600 权限原子写入配置文件。
func (c *Config) Save() error {
	p, err := Path()
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return fmt.Errorf("序列化配置失败: %w", err)
	}
	tmp := p + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return fmt.Errorf("写入配置失败: %w", err)
	}
	if err := os.Rename(tmp, p); err != nil {
		return fmt.Errorf("替换配置文件失败: %w", err)
	}
	return nil
}

// Find 按名称查找 Profile。
func (c *Config) Find(name string) (Profile, bool) {
	for _, p := range c.Profiles {
		if p.Name == name {
			return p, true
		}
	}
	return Profile{}, false
}

// Upsert 按名称插入或更新一个 Profile。
func (c *Config) Upsert(p Profile) {
	for i := range c.Profiles {
		if c.Profiles[i].Name == p.Name {
			c.Profiles[i] = p
			return
		}
	}
	c.Profiles = append(c.Profiles, p)
}

// Delete 按名称删除 Profile。
func (c *Config) Delete(name string) {
	out := c.Profiles[:0]
	for _, p := range c.Profiles {
		if p.Name != name {
			out = append(out, p)
		}
	}
	c.Profiles = out
}

// Names 返回所有 Profile 名称,供下拉框使用。
func (c *Config) Names() []string {
	names := make([]string, 0, len(c.Profiles))
	for _, p := range c.Profiles {
		names = append(names, p.Name)
	}
	return names
}
