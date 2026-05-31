"""活动日志 —— 把后端"正在发生什么"汇成一条可观测的流。

设计:给 `dst_serverd` 日志器挂一个 FileHandler 写到 logs/activity.log。于是所有
`dst_serverd.*` 子日志器(supervisor / instances / install / jobs ...)的 log.info
都会自动落进同一条流;安装/更新子进程的每行输出也经 `dst_serverd.install` 打进来。
前端用 WS 跟随这条流、用 GET 拉取做初始填充与复制 —— 管理员一眼看清流程与系统状态。
"""

from __future__ import annotations

import logging
from pathlib import Path

ACTIVITY_LOGGER = "dst_serverd"
_HANDLER_FLAG = "_dstd_activity"


def setup_activity_log(path: Path) -> Path:
    """给 dst_serverd 日志器挂活动文件 handler(幂等,避免 reload 重复挂)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(ACTIVITY_LOGGER)
    logger.setLevel(logging.INFO)
    for h in logger.handlers:
        if getattr(h, _HANDLER_FLAG, False):
            return path
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
    setattr(fh, _HANDLER_FLAG, True)
    logger.addHandler(fh)
    return path


def read_tail(path: Path, n: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except FileNotFoundError:
        return []


# 安装/更新子进程逐行输出走这个子日志器(→ 汇入活动流)
install_logger = logging.getLogger("dst_serverd.install")
