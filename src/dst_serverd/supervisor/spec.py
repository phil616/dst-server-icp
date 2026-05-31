"""ShardSpec —— 一个 Shard 进程的启动描述。

它被序列化为 `<run>/<cluster>__<shard>.spec.json`,作用有二:
1. 启动时按它拼出官方启动参数(见 DESIGN.md 1.8 / 2.3);
2. 后端重启后,reconcile 读它来重新接管 / 按期望状态补起进程。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


def shard_key(cluster: str, shard: str) -> str:
    """注册表与文件名用的稳定标识。"""
    return f"{cluster}/{shard}"


def _safe(name: str) -> str:
    return name.replace("/", "_").replace(" ", "_")


@dataclass(slots=True)
class ShardSpec:
    cluster: str
    shard: str  # Master / Caves / ...
    dst_bin: str  # 可执行文件绝对路径
    bin_cwd: str  # 工作目录,必须是 server/bin64(游戏强制要求)
    persistent_storage_root: str
    conf_dir: str
    ugc_directory: str
    # 期望状态:running 时 reconcile 会保证它在跑(见 DESIGN.md 2.10)
    desired_running: bool = True
    extra_args: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return shard_key(self.cluster, self.shard)

    @property
    def stem(self) -> str:
        return f"{_safe(self.cluster)}__{_safe(self.shard)}"

    def argv(self) -> list[str]:
        """运行态 Shard 的启动参数:一律 -skip_update_server_mods(MOD 更新交给 updater 子进程)。"""
        return [
            self.dst_bin,
            "-console",
            "-skip_update_server_mods",
            "-ugc_directory",
            self.ugc_directory,
            "-persistent_storage_root",
            self.persistent_storage_root,
            "-conf_dir",
            self.conf_dir,
            "-cluster",
            self.cluster,
            "-shard",
            self.shard,
            *self.extra_args,
        ]

    def cmdline_marker(self) -> str:
        """用于 PID 复用校验:真实 cmdline 必须同时包含 cluster 与 shard 标记。"""
        return f"-cluster {self.cluster}"

    # ---- 序列化 ----
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)  # 原子替换

    @classmethod
    def load(cls, path: Path) -> ShardSpec:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)
