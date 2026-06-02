"""日志 tail —— 读 Shard 控制台日志,带 offset 持久化 + 关键事件解析(见 DESIGN.md 2.7)。

offset 落在 `<log>.offset`,使后端重启后从上次位置续读,不重放历史。
事件解析覆盖就绪判定与玩家进出等;模式以官方日志为准,可按实际日志增补。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 关键日志模式(基于 DST 专用服务器日志,后续可按真实输出微调)
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sim_paused", re.compile(r"\bSim paused\b")),
    ("sim_unpaused", re.compile(r"\bSim unpaused\b")),
    ("shard_ready", re.compile(r"Sim paused")),  # Master 就绪信号
    ("shard_listening", re.compile(r"Telling Client our new session identifier")),
    ("secondary_connected", re.compile(r"Reconnecting|Now connected to a server|RegisterUserInWorld")),
    ("world_gen", re.compile(r"\[Shard\] .*Received world")),
    ("player_join", re.compile(r"\[Join Announcement\]\s*(?P<name>.+)")),
    ("player_leave", re.compile(r"\[Leave Announcement\]\s*(?P<name>.+)")),
    ("player_id", re.compile(r"(?P<ku>KU_[A-Za-z0-9_-]{8,})")),
    ("mod_enabling", re.compile(r"modoverrides\.lua enabling (?P<ref>\S+)")),
    # 真实日志:`Loading mod: workshop-XXXX (Name) Version:1.2.3` —— 确认已加载到游戏。
    # 版本号可能含空格(部分 MOD 把整串写进 modinfo 的 version 字段,如 "under the weather pt.1 v1.5.4.1"),
    # 故取冒号后到行尾的全部内容(process.py 会 .strip()),不能用 \S+ 在首个空格处截断。
    ("mod_loaded", re.compile(r"Loading mod:\s*(?P<ref>\S+)\s*\((?P<name>.+?)\)\s*Version:(?P<version>.+)")),
    ("mod_failed", re.compile(r"(?:Disabling (?P<ref>workshop-\S+)|(?P<ref2>workshop-\S+)[^\n]*failed to load)")),
    ("crash", re.compile(r"\[Error\]|Assert failure|SCRIPT ERROR|Stack traceback")),
    ("shutdown", re.compile(r"Shutting down")),
]


@dataclass(slots=True)
class LogEvent:
    kind: str
    line: str
    groups: dict[str, str]


def parse_line(line: str) -> list[LogEvent]:
    events: list[LogEvent] = []
    for kind, pat in _PATTERNS:
        m = pat.search(line)
        if m:
            events.append(LogEvent(kind=kind, line=line.rstrip("\n"), groups=m.groupdict()))
    return events


class LogTailer:
    """单个 Shard 日志的增量读取器。"""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.offset_path = log_path.with_suffix(log_path.suffix + ".offset")
        self._offset = self._load_offset()

    def _load_offset(self) -> int:
        try:
            return int(self.offset_path.read_text())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_offset(self) -> None:
        try:
            self.offset_path.write_text(str(self._offset))
        except OSError:
            pass

    def reset_to_end(self) -> None:
        """首次启动一个全新 Shard 时,从文件末尾开始(忽略上一世代日志)。"""
        try:
            self._offset = self.log_path.stat().st_size
        except FileNotFoundError:
            self._offset = 0
        self._save_offset()

    def read_new(self) -> list[str]:
        """返回自上次以来新增的完整行;更新并落盘 offset。"""
        try:
            size = self.log_path.stat().st_size
        except FileNotFoundError:
            return []
        if size < self._offset:
            # 日志被轮转/截断,从头读
            self._offset = 0
        if size == self._offset:
            return []
        with self.log_path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self._offset)
            chunk = fh.read()
            self._offset = fh.tell()
        self._save_offset()
        lines = chunk.splitlines()
        # 若结尾不是换行,最后一段是半行,退回 offset 等下次读全
        if chunk and not chunk.endswith("\n") and lines:
            half = lines.pop()
            self._offset -= len(half.encode("utf-8"))
            self._save_offset()
        return lines

    def poll_events(self) -> list[LogEvent]:
        events: list[LogEvent] = []
        for line in self.read_new():
            events.extend(parse_line(line))
        return events
