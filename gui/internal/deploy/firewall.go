// firewall.go —— 远端“系统防火墙”的检测、放行端口与关闭操作。
//
// 注意:这里操作的是【操作系统层】防火墙(ufw / firewalld / nftables / iptables),
// 不是云服务商的【安全组】。两者相互独立:即便系统防火墙放行了端口,
// 云控制台的安全组仍可能拦截,需要用户另行在云控制台放行。
package deploy

import (
	"context"
	"fmt"
	"strings"

	"dst-deployer/internal/config"
)

// FirewallInfo 是一次防火墙检测的结构化结果。
type FirewallInfo struct {
	Kind   string // ufw / firewalld / nftables / iptables / none
	Active bool   // 是否处于“启用/有拦截规则”状态
}

// 检测脚本:输出人类可读说明 + 形如 FW_KIND=xxx / FW_ACTIVE=0|1 的机读标记。
const detectFirewallScript = `
if command -v ufw >/dev/null 2>&1; then
  echo "FW_KIND=ufw"
  st="$(ufw status 2>/dev/null | head -n1)"
  echo "检测到 ufw,当前状态:$st"
  if ufw status 2>/dev/null | head -n1 | grep -qi active; then echo "FW_ACTIVE=1"; else echo "FW_ACTIVE=0"; fi
elif command -v firewall-cmd >/dev/null 2>&1; then
  echo "FW_KIND=firewalld"
  if firewall-cmd --state >/dev/null 2>&1; then echo "检测到 firewalld:运行中"; echo "FW_ACTIVE=1"; else echo "检测到 firewalld:未运行"; echo "FW_ACTIVE=0"; fi
elif command -v nft >/dev/null 2>&1 && [ -n "$(nft list ruleset 2>/dev/null)" ]; then
  echo "FW_KIND=nftables"
  echo "检测到 nftables 规则集"
  echo "FW_ACTIVE=1"
elif command -v iptables >/dev/null 2>&1; then
  echo "FW_KIND=iptables"
  pol="$(iptables -S INPUT 2>/dev/null | grep "^-P INPUT" | awk '{print $3}')"
  cnt="$(iptables -S INPUT 2>/dev/null | grep -c "^-A")"
  echo "检测到 iptables,INPUT 默认策略:${pol:-未知},已有规则数:${cnt:-0}"
  if [ "${pol:-ACCEPT}" != "ACCEPT" ] || [ "${cnt:-0}" -gt 0 ]; then echo "FW_ACTIVE=1"; else echo "FW_ACTIVE=0"; fi
else
  echo "FW_KIND=none"
  echo "未检测到常见的系统防火墙(ufw / firewalld / nftables / iptables)"
  echo "FW_ACTIVE=0"
fi
`

// DetectFirewall 检测远端系统防火墙类型与状态。
// FW_* 标记行用于解析,不展示给用户;其余说明行照常进日志。
func (d *Deployer) DetectFirewall(ctx context.Context, p config.Profile) (FirewallInfo, error) {
	var info FirewallInfo
	cli, err := d.connect(ctx, p)
	if err != nil {
		return info, err
	}
	defer cli.Close()

	d.log.Infof("▶ 检测系统防火墙")
	err = cli.Run(ctx, detectFirewallScript, d.useSudo, func(line string) {
		switch {
		case strings.HasPrefix(line, "FW_KIND="):
			info.Kind = strings.TrimSpace(strings.TrimPrefix(line, "FW_KIND="))
		case strings.HasPrefix(line, "FW_ACTIVE="):
			info.Active = strings.TrimSpace(strings.TrimPrefix(line, "FW_ACTIVE=")) == "1"
		default:
			d.log.Raw(line) // 仅展示人类可读的说明
		}
	})
	if err != nil {
		d.log.Errorf("✗ 检测防火墙失败: %v", err)
		return info, err
	}
	d.log.Infof("✓ 检测完成:防火墙=%s,活动=%v", fwName(info.Kind), info.Active)
	return info, nil
}

// AllowPort 在系统防火墙放行指定端口(可选 TCP / UDP)。脚本内部自动识别防火墙类型。
func (d *Deployer) AllowPort(ctx context.Context, p config.Profile, port int, tcp, udp bool) error {
	var protos []string
	if tcp {
		protos = append(protos, "tcp")
	}
	if udp {
		protos = append(protos, "udp")
	}
	if len(protos) == 0 {
		return fmt.Errorf("至少选择一种协议(TCP / UDP)")
	}
	cli, err := d.connect(ctx, p)
	if err != nil {
		return err
	}
	defer cli.Close()

	script := fmt.Sprintf("PORT=%d\nPROTOS=\"%s\"\n%s", port, strings.Join(protos, " "), allowPortScript)
	return d.run(ctx, cli, fmt.Sprintf("放行端口 %d/(%s)", port, strings.Join(protos, ",")), script)
}

const allowPortScript = `
persist_iptables() {
  if command -v netfilter-persistent >/dev/null 2>&1; then netfilter-persistent save >/dev/null 2>&1 && echo "已用 netfilter-persistent 持久化规则";
  elif [ -d /etc/iptables ]; then iptables-save > /etc/iptables/rules.v4 2>/dev/null && echo "已写入 /etc/iptables/rules.v4";
  elif command -v service >/dev/null 2>&1 && service iptables save >/dev/null 2>&1; then echo "已用 service iptables save 持久化规则";
  else echo "[提示] 未找到持久化方式,规则在重启后可能丢失"; fi
}
if command -v ufw >/dev/null 2>&1; then
  for pr in $PROTOS; do ufw allow ${PORT}/${pr} && echo "ufw 已放行 ${PORT}/${pr}"; done
elif command -v firewall-cmd >/dev/null 2>&1; then
  args=""; for pr in $PROTOS; do args="$args --add-port=${PORT}/${pr}"; done
  firewall-cmd --permanent $args && firewall-cmd --reload && echo "firewalld 已放行 ${PORT}/(${PROTOS})并重载"
elif command -v nft >/dev/null 2>&1 && [ -n "$(nft list ruleset 2>/dev/null)" ]; then
  for pr in $PROTOS; do
    nft add rule inet filter input ${pr} dport ${PORT} accept 2>/dev/null \
      && echo "nftables 已在 inet filter input 放行 ${PORT}/${pr}" \
      || echo "[警告] nftables 放行失败,可能链名不是 inet filter input,请手动处理 ${PORT}/${pr}"
  done
elif command -v iptables >/dev/null 2>&1; then
  for pr in $PROTOS; do
    iptables -C INPUT -p ${pr} --dport ${PORT} -j ACCEPT 2>/dev/null \
      || iptables -I INPUT -p ${pr} --dport ${PORT} -j ACCEPT
    echo "iptables 已放行 ${PORT}/${pr}"
  done
  persist_iptables
else
  echo "未检测到系统防火墙,无需在系统层放行端口 ${PORT}。"
  echo "请确认云服务商【安全组】已放行 ${PORT}(TCP/UDP)。"
fi
`

// DisableFirewall 关闭/停用远端系统防火墙(脚本内部自动识别类型)。
func (d *Deployer) DisableFirewall(ctx context.Context, p config.Profile) error {
	cli, err := d.connect(ctx, p)
	if err != nil {
		return err
	}
	defer cli.Close()
	return d.run(ctx, cli, "关闭系统防火墙", disableFirewallScript)
}

const disableFirewallScript = `
if command -v ufw >/dev/null 2>&1; then
  ufw --force disable && echo "ufw 已关闭"
elif command -v firewall-cmd >/dev/null 2>&1; then
  systemctl stop firewalld 2>/dev/null; systemctl disable firewalld 2>/dev/null
  echo "firewalld 已停止并取消开机自启"
elif command -v nft >/dev/null 2>&1 && [ -n "$(nft list ruleset 2>/dev/null)" ]; then
  systemctl stop nftables 2>/dev/null
  nft flush ruleset 2>/dev/null && echo "nftables 规则已清空"
elif command -v iptables >/dev/null 2>&1; then
  iptables -P INPUT ACCEPT; iptables -P FORWARD ACCEPT; iptables -P OUTPUT ACCEPT
  iptables -F
  command -v ip6tables >/dev/null 2>&1 && { ip6tables -P INPUT ACCEPT; ip6tables -P FORWARD ACCEPT; ip6tables -P OUTPUT ACCEPT; ip6tables -F; }
  echo "iptables 规则已清空、默认策略改为 ACCEPT"
  if command -v netfilter-persistent >/dev/null 2>&1; then netfilter-persistent save >/dev/null 2>&1; fi
else
  echo "未检测到系统防火墙,无需关闭。"
fi
`

// fwName 把内部 kind 转成中文展示名。
func fwName(kind string) string {
	switch kind {
	case "ufw":
		return "ufw"
	case "firewalld":
		return "firewalld"
	case "nftables":
		return "nftables"
	case "iptables":
		return "iptables"
	case "none", "":
		return "未检测到"
	default:
		return kind
	}
}
