"""ShardProcess —— 单个 Shard 游戏进程的全生命周期托管。

要点(见 DESIGN.md 2.1 / 2.3 / 2.10):
- 用 `subprocess.Popen(start_new_session=True)`(= setsid)把游戏拉成**独立会话**的进程,
  使其在后端重启期间存活,且不受 SIGHUP 影响。
- stdin 接 FIFO(命令通道与后端解耦);stdout/stderr 重定向到日志文件(后端另行 tail)。
- 优雅停服:写 FIFO `c_shutdown(true)` 让其保存后自退;超时再 SIGTERM→SIGKILL 兜底到进程组。
- 重新接管:后端重启后凭 PID 文件 + cmdline 校验确认存活,再绑定 FIFO/日志,无需重启游戏。
- 运行态 Shard **绝不注入代理环境变量**(代理只用于下载/更新,见 DESIGN.md 2.9)。
"""

from __future__ import annotations

import enum
import os
import signal
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import psutil

from . import pidfile
from .fifo import FifoChannel
from .logtail import LogEvent, LogTailer, parse_line
from .monitor import ProcSample
from .spec import ShardSpec

# 运行态 Shard 启动时要从环境里剔除的代理变量(硬边界:游戏流量绝不走代理)
_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "ftp_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "FTP_PROXY",
)


# 昵称↔KU_ 就近配对的时间窗(秒):连接日志里 KU_ 与"加入公告"通常相隔不到 1s;
# 设窗可排除服务端启动期 token 等陈旧 KU_ 与稍后某次加入被错误配对。
_PAIR_WINDOW = 15.0


class ShardState(str, enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    READY = "ready"  # Master 见到 Sim paused / Secondary 已与 Master 互联
    STOPPING = "stopping"
    CRASHED = "crashed"


class ShardProcess:
    def __init__(self, spec: ShardSpec, run_dir: Path, logs_dir: Path) -> None:
        self.spec = spec
        self.run_dir = run_dir
        self.logs_dir = logs_dir

        self.fifo = FifoChannel(run_dir / f"{spec.stem}.fifo")
        self.tailer = LogTailer(logs_dir / f"{spec.stem}.log")

        self.state: ShardState = ShardState.STOPPED
        self.pid: int | None = None
        self.ready: bool = False
        self.players: set[str] = set()
        self.player_ids: dict[str, str] = {}  # name -> KU_(从日志按就近配对,可能缺失)
        self._last_ku: str = ""               # 最近见到、尚未配给某次加入的 KU_
        self._last_ku_at: float = 0.0         # 见到该 KU_ 的单调时刻(配对设时间窗,排除启动期 token 误配)
        self._pending_join: str = ""          # 已加入但还没配到 KU_ 的昵称(等待回填)
        self._pending_join_at: float = 0.0
        # ref -> {"name", "version", "status": loaded|failed}(从日志确认是否真正加载到游戏)
        self.loaded_mods: dict[str, dict] = {}

        self._popen: subprocess.Popen[bytes] | None = None
        self._ps: psutil.Process | None = None  # 缓存以获得准确 cpu_percent

    # ---- 路径 ----
    @property
    def pidfile_path(self) -> Path:
        return self.run_dir / f"{self.spec.stem}.pid"

    @property
    def spec_path(self) -> Path:
        return self.run_dir / f"{self.spec.stem}.spec.json"

    @property
    def log_path(self) -> Path:
        return self.tailer.log_path

    # ---- 启动 ----
    def start(self) -> None:
        if self.is_alive():
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.spec.save(self.spec_path)
        self.tailer.reset_to_end()  # 新世代:忽略旧日志

        # stdin ← FIFO(RDWR,子进程永不读到 EOF)
        child_stdin = self.fifo.open_child_stdin()
        # stdout/stderr → 日志文件(append)
        log_fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)

        env = {k: v for k, v in os.environ.items() if k not in _PROXY_ENV_KEYS}

        try:
            self._popen = subprocess.Popen(  # noqa: S603 受控参数
                self.spec.argv(),
                cwd=self.spec.bin_cwd,
                stdin=child_stdin,
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,  # = setsid,脱离后端会话独立运行
                env=env,
                close_fds=True,
            )
        finally:
            # 子进程已 dup,后端释放自己这两个 fd
            os.close(child_stdin)
            os.close(log_fd)

        self.pid = self._popen.pid
        self._ps = _safe_ps(self.pid)
        pidfile.write_pidfile(self.pidfile_path, self.pid, self.spec.cmdline_marker())
        self.ready = False
        self.players.clear()
        self.loaded_mods.clear()
        self.state = ShardState.STARTING

    # ---- 重新接管(后端重启后,进程仍在跑) ----
    def reattach(self) -> bool:
        rec = pidfile.read_pidfile(self.pidfile_path)
        if rec is None:
            return False
        pid, marker = rec
        if not pidfile.verify_alive(pid, marker):
            return False
        self.pid = pid
        self._ps = _safe_ps(pid)
        self._popen = None  # 非本进程的子进程,用 psutil/信号管理
        self.state = ShardState.RUNNING  # 就绪与否由后续日志确认
        # 不重建 FIFO/日志:沿用磁盘上已有的;tailer offset 续读
        self.fifo.ensure_fifo()
        self._scan_loaded_mods()  # 重新接管:补扫日志恢复"已加载 MOD"状态
        return True

    def _scan_loaded_mods(self) -> None:
        """全量扫描日志,重建 loaded_mods(用于 reattach 后恢复 MOD 加载状态)。"""
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return
        for line in text.splitlines():
            for ev in parse_line(line):
                if ev.kind in ("mod_loaded", "mod_failed"):
                    self._apply_event(ev)

    # ---- 命令注入 ----
    def send(self, command: str) -> None:
        self.fifo.send(command)

    # ---- 停止 ----
    def stop(self, *, save: bool = True, grace: float = 30.0, sigterm_grace: float = 10.0) -> None:
        if not self.is_alive():
            self._cleanup_after_exit()
            return
        self.state = ShardState.STOPPING
        # 1) 优雅:让游戏保存后自退
        try:
            self.send(f"c_shutdown({'true' if save else 'false'})")
        except OSError:
            pass
        if self._wait_exit(grace):
            self._cleanup_after_exit()
            return
        # 2) SIGTERM 进程组
        self._signal_group(signal.SIGTERM)
        if self._wait_exit(sigterm_grace):
            self._cleanup_after_exit()
            return
        # 3) SIGKILL 兜底
        self._signal_group(signal.SIGKILL)
        self._wait_exit(5.0)
        self._cleanup_after_exit()

    def kill(self) -> None:
        """强制停止:跳过优雅保存与 SIGTERM,直接 SIGKILL 整个进程组并清理。

        用于 c_shutdown/SIGTERM 失效、进程卡死等场景;不保存存档(由调用方知情)。
        """
        if not self.is_alive():
            self._cleanup_after_exit()
            return
        self.state = ShardState.STOPPING
        self._signal_group(signal.SIGKILL)
        self._wait_exit(5.0)
        self._cleanup_after_exit()

    def _wait_exit(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_alive():
                return True
            time.sleep(0.2)
        return not self.is_alive()

    def _signal_group(self, sig: int) -> None:
        if self.pid is None:
            return
        try:
            pgid = os.getpgid(self.pid)
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            # 退化为单进程信号
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                pass

    def _cleanup_after_exit(self) -> None:
        if self._popen is not None:
            try:
                self._popen.wait(timeout=1)  # 回收僵尸
            except (subprocess.TimeoutExpired, ChildProcessError):
                pass
        self.fifo.unlink()
        pidfile.remove_pidfile(self.pidfile_path)
        self.pid = None
        self._ps = None
        self._popen = None
        self.ready = False
        self.players.clear()
        self.state = ShardState.STOPPED

    # ---- 存活与轮询 ----
    def is_alive(self) -> bool:
        if self._popen is not None:
            return self._popen.poll() is None
        if self.pid is None:
            return False
        return pidfile.verify_alive(self.pid, self.spec.cmdline_marker())

    def poll(self) -> list[LogEvent]:
        """周期调用:刷新存活/就绪,并返回新日志事件。"""
        alive = self.is_alive()
        if not alive and self.state in (ShardState.STARTING, ShardState.RUNNING, ShardState.READY):
            # 非预期退出
            self.state = ShardState.CRASHED if self.spec.desired_running else ShardState.STOPPED
            self.pid = None
            self._popen = None
        events = self.tailer.poll_events()
        for ev in events:
            self._apply_event(ev)
        if alive and self.state == ShardState.STARTING and self.ready:
            self.state = ShardState.READY
        elif alive and self.state == ShardState.STARTING:
            self.state = ShardState.RUNNING
        return events

    def _apply_event(self, ev: LogEvent) -> None:
        if ev.kind in ("sim_paused", "shard_ready"):
            self.ready = True
            if self.is_alive():
                self.state = ShardState.READY
        elif ev.kind == "player_id":
            # 连接/鉴权阶段的 KU_ 行通常先于"加入公告"出现:暂存,留给随后的加入配对。
            # 若加入公告反而先到(_pending_join 仍在时间窗内),就地回填并把昵称回写进事件供入册。
            ku = (ev.groups.get("ku") or "").strip()
            if ku:
                now = time.monotonic()
                if self._pending_join and now - self._pending_join_at <= _PAIR_WINDOW:
                    self.player_ids[self._pending_join] = ku
                    ev.groups["name"] = self._pending_join
                    self._pending_join = ""
                else:
                    self._last_ku, self._last_ku_at = ku, now
        elif ev.kind == "player_join":
            name = (ev.groups.get("name") or "").strip()
            if name:
                self.players.add(name)
                now = time.monotonic()
                # 仅当 KU_ 是刚刚(时间窗内)见到的才配对,避免启动期 token 等陈旧 KU_ 误配
                if self._last_ku and now - self._last_ku_at <= _PAIR_WINDOW:
                    self.player_ids[name] = self._last_ku
                    ev.groups["klei_id"] = self._last_ku
                    self._last_ku = ""
                else:              # 还没见到 KU_,挂起等 player_id 回填
                    self._pending_join, self._pending_join_at = name, now
        elif ev.kind == "player_leave":
            name = (ev.groups.get("name") or "").strip()
            if name:
                self.players.discard(name)
                self.player_ids.pop(name, None)
        elif ev.kind == "mod_loaded":
            ref = ev.groups.get("ref")
            if ref:
                self.loaded_mods[ref] = {
                    "name": (ev.groups.get("name") or "").strip(),
                    "version": (ev.groups.get("version") or "").strip(),
                    "status": "loaded",
                }
        elif ev.kind == "mod_failed":
            ref = ev.groups.get("ref") or ev.groups.get("ref2")
            if ref:
                entry = self.loaded_mods.setdefault(ref, {"name": "", "version": ""})
                entry["status"] = "failed"

    def sample(self) -> ProcSample | None:
        if self.pid is None or self._ps is None:
            return None
        try:
            with self._ps.oneshot():
                return ProcSample(
                    pid=self.pid,
                    cpu_percent=self._ps.cpu_percent(interval=None),
                    rss_mb=round(self._ps.memory_info().rss / 1024 / 1024, 1),
                    num_threads=self._ps.num_threads(),
                    status=self._ps.status(),
                    create_time=self._ps.create_time(),
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None

    def status_dict(self) -> dict:
        smp = self.sample()
        return {
            "key": self.spec.key,
            "cluster": self.spec.cluster,
            "shard": self.spec.shard,
            "state": self.state.value,
            "pid": self.pid,
            "ready": self.ready,
            "desired_running": self.spec.desired_running,
            "players": sorted(self.players),
            "player_ids": dict(self.player_ids),  # name -> KU_(已配对到的)
            "loaded_mods": self.loaded_mods,
            "resource": asdict(smp) if smp else None,
        }


def _safe_ps(pid: int) -> psutil.Process | None:
    try:
        proc = psutil.Process(pid)
        proc.cpu_percent(interval=None)  # 启动 cpu 测量基线
        return proc
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
