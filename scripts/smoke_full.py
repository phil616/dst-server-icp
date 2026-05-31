#!/usr/bin/env python3
"""全栈服务层冒烟测试 —— 不经 HTTP,直接驱动 db + 服务 + 渲染 + 监管。

覆盖:创建实例(渲染 ini/lua)、端口分配、MOD(改 modoverrides)、启动/就绪、
命令注入、模拟后端重启重新接管、备份、安装更新(验证代理 env 注入)、停止、删除。

运行:  uv run python scripts/smoke_full.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dst_serverd.config import Settings  # noqa: E402
from dst_serverd.db import Database  # noqa: E402
from dst_serverd.proxy import ProxyConfig, save_proxy, load_proxy  # noqa: E402
from dst_serverd.services import install  # noqa: E402
from dst_serverd.services import backups as backup_svc  # noqa: E402
from dst_serverd.services import instances as svc  # noqa: E402
from dst_serverd.supervisor import Supervisor  # noqa: E402
from dst_serverd.supervisor.process import ShardState  # noqa: E402

HERE = Path(__file__).resolve().parent


def setup_base() -> Path:
    base = Path(tempfile.mkdtemp(prefix="dstd-full-"))
    bin_dir = base / "server" / "bin64"
    bin_dir.mkdir(parents=True)
    fake_bin = bin_dir / "dontstarve_dedicated_server_nullrenderer_x64"
    shutil.copy(HERE / "fake_dst.py", fake_bin)
    fake_bin.chmod(0o755)
    sc = base / "steamcmd"
    sc.mkdir()
    shutil.copy(HERE / "fake_steamcmd.sh", sc / "steamcmd.sh")
    (sc / "steamcmd.sh").chmod(0o755)
    return base


def wait(pred, sup, timeout=6.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        sup.poll_once()
        if pred():
            return True
        time.sleep(0.2)
    return False


def main() -> int:  # noqa: C901
    base = setup_base()
    ok = True
    try:
        settings = Settings(base=base, conf_dir="clusters", shutdown_grace=4, sigterm_grace=2)
        settings.db = base / "data" / "db.sqlite3"
        db = Database(settings.db)
        sup = Supervisor(settings, poll_interval=0.5)

        # 1) 创建实例(离线、含洞穴)→ 渲染配置
        inst = svc.create_instance(db, settings, name="Smoke Test", online=False, caves=True)
        cdir = settings.cluster_dir(inst.cluster_dir_name)
        assert (cdir / "cluster.ini").exists(), "cluster.ini 未生成"
        cini = (cdir / "cluster.ini").read_text()
        assert "shard_enabled = true" in cini and f"master_port = {inst.master_port}" in cini
        assert "is_master = true" in (cdir / "Master" / "server.ini").read_text()
        cv = (cdir / "Caves" / "server.ini").read_text()
        assert "is_master = false" in cv and "shard_enabled = true" in cv
        assert 'preset = "DST_CAVE"' in (cdir / "Caves" / "worldgenoverride.lua").read_text()
        print(f"[1] created instance #{inst.id} ({inst.cluster_dir_name}) + rendered config  OK")

        # 端口分配互不冲突
        shards = svc.get_shards(db, inst.id)
        sps = [s.server_port for s in shards]
        assert len(set(sps)) == len(sps), "server_port 冲突"
        assert all(10998 <= p <= 11018 for p in sps), "server_port 超出 LAN 可见范围"
        print(f"[1b] ports {sps} distinct & in LAN range  OK")

        # 2) MOD → modoverrides
        svc.add_mod(db, settings, inst, workshop_id="378160973", name="Global Position")
        mo = (cdir / "Master" / "modoverrides.lua").read_text()
        assert '["workshop-378160973"]' in mo and "enabled = true" in mo
        assert 'ServerModSetup("378160973")' in (
            settings.server_dir / "mods" / "dedicated_server_mods_setup.lua"
        ).read_text()
        print("[2] mod added → modoverrides + mods_setup rendered  OK")

        # 3) 启动 → 两个 Shard 就绪
        svc.start_instance(db, settings, sup, inst)
        assert wait(lambda: all(
            (sp := sup.get(inst.cluster_dir_name, s.shard_dir_name)) and sp.state == ShardState.READY
            for s in shards
        ), sup), "Shard 未全部就绪"
        print(f"[3] started {len(shards)} shards, all READY  OK")

        # 4) 命令注入
        sup.send(inst.cluster_dir_name, "Master", "c_listplayers()")
        time.sleep(0.4)
        sup.poll_once()
        master = sup.get(inst.cluster_dir_name, "Master")
        assert "recv: c_listplayers()" in master.log_path.read_text(), "命令未注入"
        print("[4] command injected to Master  OK")

        # 5) 模拟后端重启:新 Supervisor 重新接管两个 Shard
        pids = {s.shard_dir_name: sup.get(inst.cluster_dir_name, s.shard_dir_name).pid for s in shards}
        sup2 = Supervisor(settings, poll_interval=0.5)
        sup2.reconcile()
        for s in shards:
            sp2 = sup2.get(inst.cluster_dir_name, s.shard_dir_name)
            assert sp2 and sp2.pid == pids[s.shard_dir_name] and sp2.is_alive(), \
                f"{s.shard_dir_name} 接管失败"
        print(f"[5] re-attached both shards after restart {pids}  OK")

        # 6) 备份
        bk = backup_svc.backup_instance(db, settings, inst, note="smoke")
        assert Path(bk["path"]).exists() and bk["size"] > 0, "备份文件无效"
        assert len(backup_svc.list_backups(db, inst.id)) == 1
        print(f"[6] backup created ({bk['size']} bytes)  OK")

        # 7) 安装更新 + 代理 env 注入
        save_proxy(db, ProxyConfig(True, "env", "http", "127.0.0.1", 7890, "", "", "127.0.0.1"))
        res = install.update_server(settings, load_proxy(db), validate=False)
        assert res.ok, f"update_server 失败 rc={res.returncode}"
        joined = "\n".join(res.tail)
        assert "http_proxy=http://127.0.0.1:7890" in joined, f"代理未注入:\n{joined}"
        print("[7] server update ran via fake steamcmd with proxy env injected  OK")

        # 8) 停止 + 删除
        svc.stop_instance(db, sup2, inst)
        assert wait(lambda: all(
            not sup2.get(inst.cluster_dir_name, s.shard_dir_name).is_alive() for s in shards
        ), sup2), "停止失败"
        svc.delete_instance(db, settings, sup2, inst)
        assert not cdir.exists(), "Cluster 目录未删除"
        assert svc.get_instance(db, inst.id) is None, "DB 行未删除"
        print("[8] stopped + deleted (dir & db cleaned)  OK")

        print("\n✅ full smoke test PASSED")
    except AssertionError as exc:
        ok = False
        print(f"\n❌ FAILED: {exc}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
