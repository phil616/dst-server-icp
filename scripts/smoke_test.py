#!/usr/bin/env python3
"""端到端冒烟测试 —— 不依赖真实 DST,验证 Supervisor 的核心管线。

覆盖:
1. setsid 启动 + 日志就绪判定(Sim paused → READY);
2. FIFO 命令注入(回显出现在日志);
3. 模拟"后端重启":新建 Supervisor → reconcile 重新接管仍存活的进程(pid 不变);
4. 优雅停服(c_shutdown → 进程退出 → FIFO/PID 文件清理)。

运行:  uv run python scripts/smoke_test.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

# 让脚本能 import src/ 下的包(无需安装)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dst_serverd.config import Settings  # noqa: E402
from dst_serverd.supervisor import Supervisor  # noqa: E402
from dst_serverd.supervisor.process import ShardState  # noqa: E402

HERE = Path(__file__).resolve().parent
FAKE = HERE / "fake_dst.py"


def setup_base() -> Path:
    base = Path(tempfile.mkdtemp(prefix="dstd-smoke-"))
    bin_dir = base / "server" / "bin64"
    bin_dir.mkdir(parents=True)
    # 把 fake_dst 放到真实可执行文件应在的位置
    target = bin_dir / "dontstarve_dedicated_server_nullrenderer_x64"
    shutil.copy(FAKE, target)
    target.chmod(0o755)
    (base / "ugc_mods").mkdir()
    (base / "clusters" / "MyCluster" / "Master").mkdir(parents=True)
    return base


def make_settings(base: Path) -> Settings:
    return Settings(
        base=base,
        conf_dir="clusters",
        shutdown_grace=5.0,
        sigterm_grace=3.0,
    )


def wait_for(predicate, timeout: float, sup: Supervisor) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sup.poll_once()
        if predicate():
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    base = setup_base()
    ok = True
    try:
        settings = make_settings(base)
        sup = Supervisor(settings, poll_interval=0.5)

        # 1) 启动 + 就绪
        spec = sup.build_spec("MyCluster", "Master")
        sp = sup.start(spec)
        pid1 = sp.pid
        print(f"[1] started Master pid={pid1}")
        assert wait_for(lambda: sp.state == ShardState.READY, 5, sup), "未就绪(Sim paused)"
        print(f"    state={sp.state.value} ready={sp.ready}  OK")

        # 2) 命令注入
        assert sup.send("MyCluster", "Master", "c_listplayers()"), "注入失败"
        time.sleep(0.5)
        sup.poll_once()
        log_text = "\n".join(_tail(sp.log_path, 50))
        assert "recv: c_listplayers()" in log_text, f"日志未见回显:\n{log_text}"
        print("[2] command injected & echoed in log  OK")

        # 3) 模拟后端重启:新 Supervisor 重新接管
        sup2 = Supervisor(settings, poll_interval=0.5)
        sup2.reconcile()
        sp2 = sup2.get("MyCluster", "Master")
        assert sp2 is not None, "reconcile 未发现 Shard"
        assert sp2.pid == pid1, f"接管后 pid 变了:{sp2.pid} != {pid1}"
        assert sp2.is_alive(), "接管后进程应仍存活"
        print(f"[3] re-attached after 'backend restart' pid={sp2.pid}  OK")

        # 接管后仍可注入命令
        assert sup2.send("MyCluster", "Master", "c_save()"), "接管后注入失败"
        time.sleep(0.5)
        sup2.poll_once()
        assert "recv: c_save()" in "\n".join(_tail(sp2.log_path, 50)), "接管后命令未生效"
        print("    post-reattach command works  OK")

        # 4) 优雅停服
        assert sup2.stop("MyCluster", "Master", save=True), "停服调用失败"
        assert not sp2.is_alive(), "停服后进程应已退出"
        assert not sp2.fifo.path.exists(), "FIFO 应被清理"
        assert not sp2.pidfile_path.exists(), "PID 文件应被清理"
        print(f"[4] graceful shutdown + cleanup  OK  (state={sp2.state.value})")

        print("\n✅ smoke test PASSED")
    except AssertionError as exc:
        ok = False
        print(f"\n❌ smoke test FAILED: {exc}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


def _tail(path: Path, n: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except FileNotFoundError:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
