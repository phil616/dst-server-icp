"""psutil 监控 —— Shard 进程的资源采样(见 DESIGN.md 2.7)。"""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(slots=True)
class ProcSample:
    pid: int
    cpu_percent: float
    rss_mb: float
    num_threads: int
    status: str
    create_time: float


def sample(pid: int) -> ProcSample | None:
    """采样一次;进程不存在返回 None。

    注:cpu_percent 需要两次采样间隔才准确。Supervisor 为每个进程缓存 psutil.Process,
    这里是无状态的便捷版,首次调用 cpu_percent 可能为 0。
    """
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            return ProcSample(
                pid=pid,
                cpu_percent=proc.cpu_percent(interval=None),
                rss_mb=round(proc.memory_info().rss / 1024 / 1024, 1),
                num_threads=proc.num_threads(),
                status=proc.status(),
                create_time=proc.create_time(),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
