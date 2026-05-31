"""WebSocket 实时日志(见 DESIGN.md 2.7 / 2.8)。

两条流:
- 某 Shard 的游戏日志:/api/instances/{cluster}/shards/{shard}/logs/ws
- 全局活动流(系统在做什么 + 安装/更新输出):/api/activity/ws

实现为文件跟随:连接时回灌末尾若干字节,随后增量推送新行。独立维护读位置,
不干扰 supervisor 的 LogTailer offset。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_POLL = 0.3


async def _follow(websocket: WebSocket, log_path: Path, tail_bytes: int) -> None:
    """跟随一个日志文件并推送新行。"""
    await websocket.accept()
    pos = 0
    try:
        if log_path.exists():
            pos = max(0, log_path.stat().st_size - tail_bytes)
        while True:
            if log_path.exists():
                size = log_path.stat().st_size
                if size < pos:  # 轮转/截断
                    pos = 0
                if size > pos:
                    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                        fh.seek(pos)
                        chunk = fh.read()
                        pos = fh.tell()
                    for line in chunk.splitlines():
                        await websocket.send_text(line)
            await asyncio.sleep(_POLL)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 连接异常即结束
        return


@router.websocket("/api/instances/{cluster}/shards/{shard}/logs/ws")
async def ws_shard_logs(websocket: WebSocket, cluster: str, shard: str) -> None:
    settings = websocket.app.state.settings
    sup = websocket.app.state.supervisor
    stem = sup.build_spec(cluster, shard).stem
    await _follow(websocket, settings.logs_dir / f"{stem}.log", tail_bytes=8192)


@router.websocket("/api/activity/ws")
async def ws_activity(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    await _follow(websocket, settings.logs_dir / "activity.log", tail_bytes=16384)
