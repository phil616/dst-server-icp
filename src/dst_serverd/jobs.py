"""后台作业 —— 安装/更新等耗时操作异步跑,前端凭 job id 轮询状态 + WS 看活动流。

作业**串行执行**(一把 run_lock):同一时刻只跑一个下载/更新,避免 SteamCMD/MOD
更新相互干扰、也让活动日志清晰不交错。
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field

log = logging.getLogger("dst_serverd.jobs")


class CancelToken:
    """协作式取消句柄：把「中断请求」从 API 线程传到 worker 线程里正在跑的子进程。

    取消时直接 `killpg(SIGKILL)` 杀掉当前活跃子进程组(steamcmd/curl 等),让卡在
    断网重连里的下载作业立刻脱困。子进程由 install._run 经 bind()/unbind() 登记。
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._proc: object | None = None  # subprocess.Popen,避免在此 import subprocess

    def cancelled(self) -> bool:
        return self._event.is_set()

    def bind(self, proc: object) -> None:
        """登记当前活跃子进程;若已被取消则立即杀掉(覆盖「先取消、后起进程」的竞态)。"""
        with self._lock:
            self._proc = proc
            if self._event.is_set():
                self._kill_locked()

    def unbind(self, proc: object) -> None:
        with self._lock:
            if self._proc is proc:
                self._proc = None

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            self._kill_locked()

    def _kill_locked(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # type: ignore[attr-defined]
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()  # type: ignore[attr-defined]
            except ProcessLookupError:
                pass


# 当前作业的取消句柄(在 worker 线程上下文里设置,供 install._run 读取)。
_current_token: ContextVar[CancelToken | None] = ContextVar(
    "dstd_current_cancel_token", default=None
)


def current_cancel_token() -> CancelToken | None:
    """取当前作业的取消句柄;非作业线程返回 None。"""
    return _current_token.get()


@dataclass
class Job:
    id: int
    action: str
    status: str = "queued"  # queued | running | success | failed | canceled
    returncode: int | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def public(self) -> dict:
        return asdict(self)


class JobRunner:
    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._next = 0
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()  # 串行执行作业
        self._tokens: dict[int, CancelToken] = {}  # job_id -> 运行中作业的取消句柄

    def submit(self, action: str, fn: Callable[[], object]) -> Job:
        with self._lock:
            self._next += 1
            job = Job(self._next, action)
            self._jobs[job.id] = job
        threading.Thread(
            target=self._run, args=(job, fn), daemon=True, name=f"job-{job.id}"
        ).start()
        return job

    def _run(self, job: Job, fn: Callable[[], object]) -> None:
        if self._run_lock.locked():
            log.info("作业 #%s（%s）排队中,等待前一个作业完成…", job.id, job.action)
        token = CancelToken()
        with self._run_lock:
            # 排队→运行 的状态切换与 cancel() 互斥:期间被取消则直接跳过执行
            with self._lock:
                if job.status == "canceled":
                    log.info("⏭ 作业 #%s 排队期间已取消,跳过:%s", job.id, job.action)
                    return
                job.status = "running"
                job.started_at = time.time()
                self._tokens[job.id] = token
            _current_token.set(token)  # worker 线程上下文,供 install._run 读取
            log.info("▶ 作业 #%s 开始:%s", job.id, job.action)
            try:
                res = fn()
                if token.cancelled():
                    job.status = "canceled"
                    job.error = "已被用户强制中断"
                else:
                    rc = getattr(res, "returncode", 0)
                    job.returncode = rc
                    job.status = "success" if rc == 0 else "failed"
                    hint = getattr(res, "error_hint", "")
                    if hint and rc != 0:
                        job.error = hint
            except Exception as exc:  # noqa: BLE001 作业内异常需记录但不崩后端
                if token.cancelled():
                    job.status = "canceled"
                    job.error = "已被用户强制中断"
                else:
                    job.status = "failed"
                    job.error = str(exc)
                    log.exception("作业 #%s 异常:%s", job.id, job.action)
            finally:
                with self._lock:
                    self._tokens.pop(job.id, None)
                job.finished_at = time.time()
                dur = (job.finished_at - (job.started_at or job.finished_at))
                log.info(
                    "⏹ 作业 #%s 结束:%s status=%s rc=%s 用时%.1fs",
                    job.id, job.action, job.status, job.returncode, dur,
                )

    def list(self) -> list[dict]:
        with self._lock:
            return [j.public() for j in sorted(self._jobs.values(), key=lambda x: x.id, reverse=True)]

    def get(self, job_id: int) -> dict | None:
        with self._lock:
            j = self._jobs.get(job_id)
            return j.public() if j else None

    def cancel(self, job_id: int) -> bool:
        """中断作业。已结束(success/failed/canceled)的不可操作,返回 False。

        - 排队中:直接标记 canceled;其线程仍阻塞在 run_lock 上,待轮到它时在 _run 里
          发现 canceled 即跳过执行。
        - 执行中:取出取消句柄,killpg(SIGKILL) 杀掉当前子进程组;_run 在 fn() 返回后
          复检 token.cancelled() 把状态落为 canceled。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status == "queued":
                job.status = "canceled"
                job.finished_at = time.time()
                log.info("✋ 作业 #%s 已取消(排队中未执行):%s", job_id, job.action)
                return True
            if job.status == "running":
                token = self._tokens.get(job_id)
            else:
                return False
        # 在 self._lock 之外杀进程:killpg 可能阻塞,且 token 自带锁,无需占用 runner 锁
        if token is not None:
            token.cancel()
        log.info("✋ 强制中断执行中的作业 #%s:%s", job_id, job.action)
        return True
