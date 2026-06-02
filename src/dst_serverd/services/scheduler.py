"""自动备份调度(见 DESIGN.md 2.6:定时 + 滚动清理)。

后台 asyncio 循环,按 kv 设置周期性备份**正在运行**的实例(trigger='auto'),
并在 backup_instance 内按 retention 滚动清理。设置项:
- backup_auto_enabled  '1'/'0'(默认关)
- backup_interval_min  分钟(默认 360)
- backup_retention     保留份数(默认 10,见 backups.py)
"""

from __future__ import annotations

import asyncio
import logging
import time

from typing import TYPE_CHECKING

from ..config import Settings
from ..db import Database
from . import backups as backup_svc
from . import instances as inst_svc

if TYPE_CHECKING:
    from ..supervisor import Supervisor

log = logging.getLogger("dst_serverd.scheduler")


class BackupScheduler:
    def __init__(self, db: Database, settings: Settings, tick: float = 60.0,
                 sup: Supervisor | None = None) -> None:
        self.db = db
        self.settings = settings
        self.tick = tick
        self.sup = sup  # 自动备份的是运行中实例 → 需要它做备份前写同步(c_save)
        self._last: dict[int, float] = {}  # instance_id -> 上次自动备份(单调时刻)
        self._task: asyncio.Task[None] | None = None

    def _enabled(self) -> bool:
        return self.db.get_kv("backup_auto_enabled", "0") == "1"

    def _interval_sec(self) -> float:
        try:
            return max(5.0, float(self.db.get_kv("backup_interval_min", "360")) * 60)
        except ValueError:
            return 360 * 60

    def tick_once(self) -> None:
        if not self._enabled():
            return
        interval = self._interval_sec()
        now = time.monotonic()
        for inst in inst_svc.list_instances(self.db):
            if inst.status != "running":
                continue
            last = self._last.get(inst.id)
            if last is not None and now - last < interval:
                continue
            if last is None:
                # 首次见到:记录基线,下个周期才备份(避免启动即备份)
                self._last[inst.id] = now
                continue
            try:
                backup_svc.backup_instance(self.db, self.settings, inst, note="自动",
                                           trigger="auto", sup=self.sup)
                self._last[inst.id] = now
            except Exception:  # noqa: BLE001
                log.exception("自动备份失败 cluster=%s", inst.cluster_dir_name)

    async def run_loop(self) -> None:
        log.info("备份调度已启动(tick=%.0fs)", self.tick)
        try:
            while True:
                await asyncio.to_thread(self.tick_once)
                await asyncio.sleep(self.tick)
        except asyncio.CancelledError:
            raise

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
