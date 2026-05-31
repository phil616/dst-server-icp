"""下载/更新代理(见 DESIGN.md 2.9)。

仅作用于 SteamCMD / 服务端本体 / MOD 下载子进程,绝不作用于运行态 Shard。
两层:env(注入 http(s)_proxy)与 force(proxychains4 在 connect() 层强制路由)。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .db import Database


@dataclass(slots=True)
class ProxyConfig:
    enabled: bool
    mode: str  # off | env | force
    scheme: str  # http | https | socks5
    host: str
    port: int
    username: str
    password: str
    no_proxy: str

    @property
    def url(self) -> str:
        auth = ""
        if self.username:
            auth = self.username + (f":{self.password}" if self.password else "") + "@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    @property
    def active(self) -> bool:
        return self.enabled and self.mode != "off" and bool(self.host) and self.port > 0


def load_proxy(db: Database) -> ProxyConfig:
    r = db.query_one("SELECT * FROM proxy_config WHERE id = 1")
    if r is None:
        return ProxyConfig(False, "env", "http", "", 0, "", "", "127.0.0.1,localhost")
    return ProxyConfig(
        enabled=bool(r["enabled"]),
        mode=r["mode"],
        scheme=r["scheme"],
        host=r["host"],
        port=r["port"],
        username=r["username"],
        password=r["password"],
        no_proxy=r["no_proxy"],
    )


def save_proxy(db: Database, cfg: ProxyConfig) -> None:
    import time

    db.execute(
        "UPDATE proxy_config SET enabled=?, mode=?, scheme=?, host=?, port=?, "
        "username=?, password=?, no_proxy=?, updated_at=? WHERE id = 1",
        (
            int(cfg.enabled), cfg.mode, cfg.scheme, cfg.host, cfg.port,
            cfg.username, cfg.password, cfg.no_proxy, time.time(),
        ),
    )


def download_env(cfg: ProxyConfig, base: dict[str, str] | None = None) -> dict[str, str]:
    """构造下载子进程的环境(在当前 env 基础上叠加代理变量)。"""
    env = dict(base if base is not None else os.environ)
    if not cfg.active:
        return env
    url = cfg.url
    for key in ("http_proxy", "https_proxy", "all_proxy"):
        env[key] = url
        env[key.upper()] = url
    env["no_proxy"] = cfg.no_proxy
    env["NO_PROXY"] = cfg.no_proxy
    return env


def render_proxychains_conf(cfg: ProxyConfig, path: Path) -> Path:
    """渲染 proxychains.conf(见 DESIGN.md 3.2)。"""
    proxy_dns = "proxy_dns" if cfg.scheme == "socks5" else "# proxy_dns"
    auth = f" {cfg.username} {cfg.password}" if cfg.username else ""
    text = (
        "strict_chain\n"
        f"{proxy_dns}\n"
        "tcp_read_time_out 15000\n"
        "tcp_connect_time_out 8000\n"
        "[ProxyList]\n"
        f"{cfg.scheme} {cfg.host} {cfg.port}{auth}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def wrap_argv(cfg: ProxyConfig, argv: list[str], conf_path: Path) -> list[str]:
    """force 模式下用 proxychains4 包裹下载命令;否则原样返回。"""
    if not cfg.active or cfg.mode != "force":
        return argv
    pc = shutil.which("proxychains4") or shutil.which("proxychains")
    if not pc:
        # 没装 proxychains 时退化为 env 模式(env 已在 download_env 注入)
        return argv
    render_proxychains_conf(cfg, conf_path)
    return [pc, "-f", str(conf_path), *argv]
