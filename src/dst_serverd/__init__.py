"""DST Serverd —— 饥荒联机版专用服务器管理后端。

架构(见 DESIGN.md 第二部分):单机、无 Docker。Python 后端是唯一管理权威,
用 subprocess 直接托管每个 Shard 游戏进程,命令走 FIFO、日志走文件、存活/资源
用 psutil 监控;后端自身由 uv + systemd 托管,重启后凭 PID 文件 + FIFO + 日志
offset 重新接管已运行的 Shard,不打断玩家。
"""

__version__ = "1.0.3"
