"""后台作业 —— 安装/更新等耗时操作异步跑,前端凭 job id 轮询状态 + WS 看活动流。

作业**串行执行**(一把 run_lock):同一时刻只跑一个下载/更新,避免 SteamCMD/MOD
更新相互干扰、也让活动日志清晰不交错。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

log = logging.getLogger("dst_serverd.jobs")


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
        with self._run_lock:
            # 排队→运行 的状态切换与 cancel() 互斥:期间被取消则直接跳过执行
            with self._lock:
                if job.status == "canceled":
                    log.info("⏭ 作业 #%s 排队期间已取消,跳过:%s", job.id, job.action)
                    return
                job.status = "running"
                job.started_at = time.time()
            log.info("▶ 作业 #%s 开始:%s", job.id, job.action)
            try:
                res = fn()
                rc = getattr(res, "returncode", 0)
                job.returncode = rc
                job.status = "success" if rc == 0 else "failed"
                hint = getattr(res, "error_hint", "")
                if hint and rc != 0:
                    job.error = hint
            except Exception as exc:  # noqa: BLE001 作业内异常需记录但不崩后端
                job.status = "failed"
                job.error = str(exc)
                log.exception("作业 #%s 异常:%s", job.id, job.action)
            finally:
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
        """取消尚未开始执行的【排队中】作业。running/已完成的不可取消(返回 False)。

        被取消的作业其线程仍阻塞在 run_lock 上,待轮到它时在 _run 里发现 canceled 即跳过执行。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return False
            job.status = "canceled"
            job.finished_at = time.time()
        log.info("✋ 作业 #%s 已取消(排队中未执行):%s", job_id, job.action)
        return True
