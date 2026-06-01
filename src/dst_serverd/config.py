"""后端配置 —— 从 config.yaml 读取(见 DESIGN.md 2.10)。

不再用环境变量告诉后端 db/目录在哪;改用项目根(或 /etc/dst-serverd)的 config.yaml。
查找顺序:$DSTD_CONFIG(可选)→ ./config.yaml(cwd)→ <repo>/config.yaml → /etc/dst-serverd/config.yaml;
都没有则用内置默认值。代理配置不在这里,存于 SQLite(见 proxy.py)。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel


class Settings(BaseModel):
    # ---- DST 安装根布局(见 DESIGN.md 2.2) ----
    base: Path = Path("/opt/dst")
    conf_dir: str = "clusters"
    server_bin_name: str = "dontstarve_dedicated_server_nullrenderer_x64"

    # ---- 后端自身 ----
    host: str = "127.0.0.1"
    port: int = 8000
    db: Path = Path("data/dstd.sqlite3")
    secret_key: str = "change-me"

    # ---- 在线模式默认 cluster_token ----
    # 实例开启 online 但未单独配置 token 时,回退使用此 token 激活在线模式
    # (避免退回离线/LAN-only 而被引擎强制 server_port ∈ [10998,11018])。
    default_cluster_token: str = (
        "pds-g^KU_98gUIb6n^UTaH6k+KMbyLZAk+fmMC5mpgUvKMv4qH51wI9B8ZZgQ="
    )

    # ---- 关停超时(秒) ----
    shutdown_grace: float = 30.0
    sigterm_grace: float = 10.0

    # ---- 派生路径 ----
    @property
    def server_dir(self) -> Path:
        return self.base / "server"

    @property
    def bin_dir(self) -> Path:
        return self.server_dir / "bin64"

    @property
    def dst_bin(self) -> Path:
        return self.bin_dir / self.server_bin_name

    @property
    def steamcmd_dir(self) -> Path:
        return self.base / "steamcmd"

    @property
    def ugc_mods_dir(self) -> Path:
        return self.base / "ugc_mods"

    @property
    def clusters_dir(self) -> Path:
        return self.base / self.conf_dir

    @property
    def logs_dir(self) -> Path:
        return self.base / "logs"

    @property
    def run_dir(self) -> Path:
        """PID / FIFO / spec / offset 等运行期文件。"""
        return self.base / "run"

    def cluster_dir(self, cluster: str) -> Path:
        return self.clusters_dir / cluster


def find_config() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("DSTD_CONFIG")
    if env:
        candidates.append(Path(env))
    candidates += [
        Path.cwd() / "config.yaml",
        Path(__file__).resolve().parents[2] / "config.yaml",  # 仓库根
        Path("/etc/dst-serverd/config.yaml"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@lru_cache
def get_settings() -> Settings:
    path = find_config()
    data: dict = {}
    if path is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    s = Settings(**data)
    # 相对路径相对配置文件所在目录解析(无配置则相对 cwd),避免依赖启动时的 cwd
    cfg_dir = path.parent if path else Path.cwd()
    if not s.base.is_absolute():
        s.base = (cfg_dir / s.base).resolve()
    if not s.db.is_absolute():
        s.db = (cfg_dir / s.db).resolve()
    return s
