"""进程监管模块 —— 后端对 DST Shard 进程的全部托管能力(见 DESIGN.md 2.1 / 2.7)。

子模块:
- spec      ShardSpec:一个 Shard 的启动描述,序列化到磁盘,既用于启动也用于重新接管。
- fifo      FIFO 命令通道:进程 stdin 走命名管道,与后端生命周期解耦。
- pidfile   PID 文件读写 + /proc cmdline 校验(防 PID 复用误判)。
- monitor   psutil 存活/资源采样。
- logtail   带 offset 的日志 tail + 关键事件解析。
- process   ShardProcess:单个 Shard 的启动/停止/注入命令/重新接管。
- manager   Supervisor:所有 Shard 的注册表与对账(reconcile)。
"""

from .manager import Supervisor
from .process import ShardProcess, ShardState
from .spec import ShardSpec

__all__ = ["Supervisor", "ShardProcess", "ShardState", "ShardSpec"]
