"""FIFO 命令通道 —— Shard 进程的 stdin 走命名管道,而非裸 Popen.stdin。

为什么用 FIFO(见 DESIGN.md 2.1):
裸 `Popen.stdin` 在后端进程退出时即失效,后端一重启就再也无法向游戏注入命令。
改用 FIFO 后,进程生命周期与后端解耦 —— 后端重启后重新 open 同一个 FIFO 即可继续
注入 `c_*` 命令,无需重启游戏。

关键文件描述符约定:
- 启动 Shard 时,把它的 stdin 接到 FIFO,并用 **O_RDWR**(读写)模式打开传给子进程。
  RDWR 打开 FIFO 在 Linux 上从不阻塞,且让该 FIFO 永远存在一个写端(子进程自己),
  因此游戏永远不会在 stdin 上读到 EOF —— 即便当前没有后端连接。
- 后端注入命令时以 **O_WRONLY** 打开写端;因为子进程是读端(reader),open 立即成功。
"""

from __future__ import annotations

import errno
import os
from pathlib import Path


class FifoChannel:
    """单个 Shard 的命令注入通道。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._writer: int | None = None  # O_WRONLY fd,惰性打开并复用

    # ---- 生命周期 ----
    def ensure_fifo(self) -> None:
        """确保 FIFO 节点存在(幂等)。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            os.mkfifo(self.path, 0o600)
        elif not _is_fifo(self.path):
            raise RuntimeError(f"{self.path} 已存在但不是 FIFO")

    def open_child_stdin(self) -> int:
        """打开供子进程作为 stdin 的 fd(O_RDWR,阻塞模式)。

        返回的 fd 交给 Popen(stdin=fd);spawn 后后端应 os.close() 它,子进程持有 dup。
        子进程的 fd0 因此是 RDWR FIFO,读为命令、永不 EOF。
        """
        self.ensure_fifo()
        # 不带 O_NONBLOCK:RDWR 打开 FIFO 本就不阻塞,且子进程 stdin 应为阻塞读。
        return os.open(self.path, os.O_RDWR)

    # ---- 注入命令 ----
    def send(self, command: str) -> None:
        """向 Shard 注入一行控制台命令(自动补换行)。"""
        line = command.rstrip("\n") + "\n"
        data = line.encode("utf-8")
        try:
            os.write(self._ensure_writer(), data)
        except (BrokenPipeError, OSError):
            # 读端可能短暂消失,重开一次再试
            self._close_writer()
            os.write(self._ensure_writer(), data)

    def _ensure_writer(self) -> int:
        if self._writer is None:
            self.ensure_fifo()
            # O_WRONLY 需要存在读端;运行中的 Shard 即读端,open 立即成功。
            # 若 Shard 尚未起好,这里会抛 ENXIO(见调用方处理)。
            self._writer = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
            # 清掉 NONBLOCK,后续写以阻塞语义保证整行写入。
            flags = os.get_blocking(self._writer)
            os.set_blocking(self._writer, True)
            _ = flags
        return self._writer

    def writer_ready(self) -> bool:
        """读端(Shard)是否在线,可立即注入。"""
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno == errno.ENXIO:  # 无读端
                return False
            raise
        os.close(fd)
        return True

    # ---- 清理 ----
    def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                os.close(self._writer)
            finally:
                self._writer = None

    def close(self) -> None:
        """仅关闭后端持有的写端;不删除 FIFO(进程可能仍在用)。"""
        self._close_writer()

    def unlink(self) -> None:
        """删除 FIFO 节点(仅在确认 Shard 已停后调用)。"""
        self._close_writer()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _is_fifo(path: Path) -> bool:
    import stat

    return stat.S_ISFIFO(path.stat().st_mode)
