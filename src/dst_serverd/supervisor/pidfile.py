"""PID 文件 —— 后端重启后据此重新发现并接管 Shard(见 DESIGN.md 3.1 约束 13)。

写入 pid 与一个 cmdline 标记;读回时用 psutil 校验该 pid 仍是同一个 Shard
(防止 PID 被系统复用后误把别的进程当成 Shard)。
"""

from __future__ import annotations

import json
from pathlib import Path

import psutil


def write_pidfile(path: Path, pid: int, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"pid": pid, "marker": marker}), encoding="utf-8")
    tmp.replace(path)


def read_pidfile(path: Path) -> tuple[int, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return int(data["pid"]), str(data.get("marker", ""))


def remove_pidfile(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def verify_alive(pid: int, marker: str) -> bool:
    """该 pid 是否仍存活、且确实是带 `marker` 的 Shard 进程。"""
    try:
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False
        cmdline = " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    return marker in cmdline
