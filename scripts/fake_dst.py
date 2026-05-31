#!/usr/bin/env python3
"""伪 DST 服务端 —— 仅用于本地验证进程托管管线(FIFO/日志/接管/停服)。

行为:打印启动行 → 打印 `Sim paused`(就绪标记)→ 阻塞读 stdin 的命令行并回显;
收到 `c_shutdown...` 打印 `Shutting down` 后退出。它不依赖真实游戏,可放在
server/bin64/<server_bin_name> 位置冒充可执行文件来跑通整条链路。
"""

from __future__ import annotations

import os
import sys
import time


def emit(s: str) -> None:
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def main() -> int:
    emit("[fake-dst] starting")
    emit("[fake-dst] args: " + " ".join(sys.argv[1:]))
    time.sleep(0.2)
    # 模拟 MOD 加载日志(真实 DST 格式),用于验证"已加载到游戏"检测
    emit("modoverrides.lua enabling workshop-378160973")
    emit("Loading mod: workshop-378160973 (Demo Mod) Version:1.0.0")
    emit("Sim paused")  # 就绪标记,LogTailer 会据此判 READY

    buf = b""
    while True:
        try:
            chunk = os.read(0, 4096)  # stdin = RDWR FIFO,阻塞等待命令
        except OSError:
            time.sleep(0.1)
            continue
        if not chunk:
            time.sleep(0.05)
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            cmd = raw.decode("utf-8", "replace").strip()
            if not cmd:
                continue
            emit(f"[fake-dst] recv: {cmd}")
            if cmd.startswith("c_shutdown"):
                emit("Shutting down")
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
