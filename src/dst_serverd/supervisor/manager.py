"""Supervisor —— 所有 Shard 的注册表、对账(reconcile)与监管循环。

后端是唯一管理权威(见 DESIGN.md 2.7 / 2.10):
- 启动时 reconcile:扫描 run_dir 的 spec,对仍存活的 Shard 重新接管,对期望运行但已不在的
  按 spec 重新拉起 —— 实现"期望状态 = running 就保持在跑"。
- 监管循环:周期轮询每个 Shard 的存活/日志事件;对"非预期崩溃且期望运行"的做带退避的自动重启。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Iterable

import psutil

from ..config import Settings
from ..db import Database
from .process import ShardProcess, ShardState
from .spec import ShardSpec, shard_key

log = logging.getLogger("dst_serverd.supervisor")


def _argv_has(cmd: list[str], flag: str, value: str) -> bool:
    """argv 中存在 `flag value` 相邻对(精确相等,避免前缀名相互误伤)。"""
    return any(cmd[i] == flag and cmd[i + 1] == value for i in range(len(cmd) - 1))


class Supervisor:
    def __init__(self, settings: Settings, poll_interval: float = 2.0,
                 db: Database | None = None) -> None:
        self.settings = settings
        self.poll_interval = poll_interval
        self.db = db  # 有 db 时,玩家加入即自动记入本地通讯录(见 _log_events)
        self._shards: dict[str, ShardProcess] = {}
        self._lock = threading.RLock()
        self._restart_after: dict[str, float] = {}  # key -> 最早可重启的单调时刻
        self._last_state: dict[str, str] = {}  # key -> 上次状态(用于打印流转)
        self._loop_task: asyncio.Task[None] | None = None

    # ---- spec 构建 ----
    def build_spec(
        self, cluster: str, shard: str, *, extra_args: Iterable[str] | None = None
    ) -> ShardSpec:
        s = self.settings
        return ShardSpec(
            cluster=cluster,
            shard=shard,
            dst_bin=str(s.dst_bin),
            bin_cwd=str(s.bin_dir),
            persistent_storage_root=str(s.base),
            conf_dir=s.conf_dir,
            ugc_directory=str(s.ugc_mods_dir),
            desired_running=True,
            extra_args=list(extra_args or []),
        )

    # ---- 注册表 ----
    def get(self, cluster: str, shard: str) -> ShardProcess | None:
        return self._shards.get(shard_key(cluster, shard))

    def all(self) -> list[ShardProcess]:
        with self._lock:
            return list(self._shards.values())

    def _ensure(self, spec: ShardSpec) -> ShardProcess:
        sp = self._shards.get(spec.key)
        if sp is None:
            sp = ShardProcess(spec, self.settings.run_dir, self.settings.logs_dir)
            self._shards[spec.key] = sp
        else:
            sp.spec = spec
        return sp

    # ---- 生命周期动作 ----
    def start(self, spec: ShardSpec) -> ShardProcess:
        with self._lock:
            spec.desired_running = True
            sp = self._ensure(spec)
            sp.spec.desired_running = True
            sp.spec.save(sp.spec_path)
            sp.start()
            self._restart_after.pop(spec.key, None)
            log.info("started shard %s pid=%s", spec.key, sp.pid)
            return sp

    def stop(self, cluster: str, shard: str, *, save: bool = True, force: bool = False) -> bool:
        with self._lock:
            sp = self.get(cluster, shard)
            if sp is None:
                # 注册表里没有(reattach 失败/句柄丢失):仍做系统层兜底清理
                self.kill_orphans(cluster, shard)
                return False
            sp.spec.desired_running = False
            sp.spec.save(sp.spec_path)
            if force:
                sp.kill()
            else:
                sp.stop(
                    save=save,
                    grace=self.settings.shutdown_grace,
                    sigterm_grace=self.settings.sigterm_grace,
                )
            # 兜底:清理任何仍匹配该 cluster/shard 的残留进程(僵尸/句柄丢失)
            self.kill_orphans(cluster, shard)
            self._restart_after.pop(sp.spec.key, None)
            log.info("stopped shard %s (force=%s)", sp.spec.key, force)
            return True

    def kill_orphans(self, cluster: str, shard: str | None = None) -> int:
        """系统层兜底:SIGKILL 掉 argv 匹配该 cluster(可选 shard)的 DST 进程。

        覆盖 supervisor 句柄丢失、reattach 失败、上次崩溃残留等情况——这些进程占着
        UDP 端口却不在注册表里,导致重启报 SOCKET_PORT_ALREADY_IN_USE。返回杀掉的数量。
        """
        killed = 0
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmd = proc.info["cmdline"] or []
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if not _argv_has(cmd, "-cluster", cluster):
                continue
            if shard is not None and not _argv_has(cmd, "-shard", shard):
                continue
            try:
                proc.kill()
                killed += 1
                log.warning("kill_orphans: SIGKILL pid=%s cluster=%s shard=%s", proc.pid, cluster, shard)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return killed

    def remove(self, cluster: str, shard: str) -> None:
        """停止 Shard 并清除其 spec/注册项(用于删除实例)。"""
        with self._lock:
            sp = self.get(cluster, shard)
            if sp is None:
                return
            sp.spec.desired_running = False
            sp.stop(save=False, grace=self.settings.shutdown_grace,
                    sigterm_grace=self.settings.sigterm_grace)
            sp.spec_path.unlink(missing_ok=True)
            self._shards.pop(sp.spec.key, None)
            self._restart_after.pop(sp.spec.key, None)
            self._last_state.pop(sp.spec.key, None)
            log.info("removed shard %s", f"{cluster}/{shard}")

    def restart(self, cluster: str, shard: str) -> ShardProcess | None:
        with self._lock:
            sp = self.get(cluster, shard)
            if sp is None:
                return None
            spec = sp.spec
            sp.stop(save=True, grace=self.settings.shutdown_grace,
                    sigterm_grace=self.settings.sigterm_grace)
            spec.desired_running = True
            sp.start()
            return sp

    def send(self, cluster: str, shard: str, command: str) -> bool:
        sp = self.get(cluster, shard)
        if sp is None or not sp.is_alive():
            return False
        sp.send(command)
        return True

    # ---- 对账 ----
    def reconcile(self) -> None:
        """启动时调用:从磁盘 spec 重建注册表,接管存活进程、补起缺失进程。"""
        run_dir = self.settings.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            for spec_path in sorted(run_dir.glob("*.spec.json")):
                try:
                    spec = ShardSpec.load(spec_path)
                except Exception:  # noqa: BLE001 跳过损坏 spec
                    log.exception("bad spec %s", spec_path)
                    continue
                sp = self._ensure(spec)
                if sp.reattach():
                    log.info("reattached shard %s pid=%s", spec.key, sp.pid)
                elif spec.desired_running:
                    log.info("desired running but not alive, starting %s", spec.key)
                    try:
                        sp.start()
                    except Exception:  # noqa: BLE001
                        log.exception("failed to start %s during reconcile", spec.key)
                else:
                    sp.state = ShardState.STOPPED

    # ---- 监管循环 ----
    def poll_once(self) -> None:
        with self._lock:
            shards = list(self._shards.values())
        now = time.monotonic()
        for sp in shards:
            try:
                events = sp.poll()
            except Exception:  # noqa: BLE001
                log.exception("poll error for %s", sp.spec.key)
                continue
            self._log_transition(sp)
            self._log_events(sp, events)
            if sp.state == ShardState.CRASHED and sp.spec.desired_running:
                ready_at = self._restart_after.get(sp.spec.key)
                if ready_at is None:
                    # 安排一次退避重启
                    self._restart_after[sp.spec.key] = now + 5.0
                    log.warning("shard %s crashed; restart scheduled in 5s", sp.spec.key)
                elif now >= ready_at:
                    log.warning("auto-restarting crashed shard %s", sp.spec.key)
                    self._restart_after.pop(sp.spec.key, None)
                    try:
                        sp.start()
                    except Exception:  # noqa: BLE001
                        log.exception("auto-restart failed for %s", sp.spec.key)
                        self._restart_after[sp.spec.key] = now + 15.0

    _STATE_CN = {
        "starting": "启动中", "running": "运行中", "ready": "就绪",
        "stopping": "停止中", "crashed": "已崩溃", "stopped": "已停止",
    }

    def _log_transition(self, sp: ShardProcess) -> None:
        key = sp.spec.key
        new = sp.state.value
        old = self._last_state.get(key)
        if old == new:
            return
        self._last_state[key] = new
        if old is None and new in ("running", "starting"):
            return  # 刚 start 已单独记过
        icon = {"ready": "✓", "crashed": "✗", "stopped": "■"}.get(new, "·")
        log.info("%s Shard %s 状态:%s → %s%s", icon, key,
                 self._STATE_CN.get(old or "", old or "—"), self._STATE_CN.get(new, new),
                 f" pid={sp.pid}" if sp.pid else "")

    def _record_contact(self, name: str, klei_id: str) -> None:
        """玩家加入 → 自动记入本地通讯录(昵称↔Klei ID)。失败不影响监管。"""
        if not (self.db and klei_id):
            return
        try:
            from ..services import contacts
            contacts.record_seen(self.db, klei_id, name)
        except Exception:  # noqa: BLE001 通讯录是附属功能,绝不拖垮监管循环
            log.debug("record contact failed", exc_info=True)

    def _log_events(self, sp: ShardProcess, events) -> None:
        key = sp.spec.key
        for ev in events:
            if ev.kind == "player_join":
                log.info("👤 Shard %s 玩家加入:%s", key, ev.groups.get("name", "?"))
                # process.py 已就近把 KU_ 配进 groups["klei_id"](若已知)
                self._record_contact(ev.groups.get("name", ""), ev.groups.get("klei_id", ""))
            elif ev.kind == "player_id":
                # KU_ 行晚于加入公告时,process.py 会回填 groups["name"],在此入册
                if ev.groups.get("name"):
                    self._record_contact(ev.groups["name"], ev.groups.get("ku", ""))
            elif ev.kind == "player_leave":
                log.info("👋 Shard %s 玩家离开:%s", key, ev.groups.get("name", "?"))
            elif ev.kind == "secondary_connected":
                log.info("🔗 Shard %s 已与 Master 互联", key)
            elif ev.kind == "crash":
                log.warning("💥 Shard %s 日志报错:%s", key, ev.line[:200])

    async def run_loop(self) -> None:
        log.info("supervisor loop started (interval=%.1fs)", self.poll_interval)
        try:
            while True:
                await asyncio.to_thread(self.poll_once)
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            log.info("supervisor loop stopped")
            raise

    def start_loop(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self.run_loop())

    async def stop_loop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

    def status(self) -> list[dict]:
        with self._lock:
            return [sp.status_dict() for sp in self._shards.values()]
