#!/usr/bin/env python3
"""MOD 更新检测 + 已加载检测 冒烟测试(Steam API 用桩,不依赖网络)。

覆盖:
1. 从服务器日志检测"MOD 真正加载到游戏"(名称 + 版本);
2. update_status 状态机(unchecked → unknown → latest → outdated);
3. check_updates 回填 / mark_all_installed_current 对齐基线(fetch 打桩)。

运行:  uv run python scripts/smoke_modupdate.py
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
from dst_serverd.services import instances as svc  # noqa: E402
from dst_serverd.services import modupdate  # noqa: E402
from dst_serverd.supervisor import Supervisor  # noqa: E402
from dst_serverd.supervisor.process import ShardState  # noqa: E402

HERE = Path(__file__).resolve().parent
WID = "378160973"


def setup_base() -> Path:
    base = Path(tempfile.mkdtemp(prefix="dstd-modupd-"))
    bin_dir = base / "server" / "bin64"
    bin_dir.mkdir(parents=True)
    fake = bin_dir / "dontstarve_dedicated_server_nullrenderer_x64"
    shutil.copy(HERE / "fake_dst.py", fake)
    fake.chmod(0o755)
    (base / "ugc_mods").mkdir()
    (base / "clusters").mkdir()
    return base


def main() -> int:  # noqa: C901
    base = setup_base()
    ok = True
    fake_time = {"v": 1000}

    def fake_fetch(_db, ids, timeout=15.0):
        return {wid: {"time_updated": fake_time["v"], "title": f"Mod {wid}", "file_size": 1234}
                for wid in ids if wid.isdigit()}

    modupdate.fetch_workshop_details = fake_fetch  # 打桩,避免真实网络

    try:
        settings = Settings(base=base, conf_dir="clusters", shutdown_grace=4, sigterm_grace=2)
        settings.db = base / "db.sqlite3"
        db = Database(settings.db)

        inst = svc.create_instance(db, settings, name="ModUpd", online=False, caves=False)
        svc.add_mod(db, settings, inst, workshop_id=WID, name="Demo")

        # 1) 启动 → 从日志检测"已加载到游戏"
        sup = Supervisor(settings, poll_interval=0.4)
        svc.start_instance(db, settings, sup, inst)
        end = time.monotonic() + 5
        while time.monotonic() < end:
            sup.poll_once()
            sp = sup.get(inst.cluster_dir_name, "Master")
            if sp and sp.state == ShardState.READY and sp.loaded_mods:
                break
            time.sleep(0.2)
        sp = sup.get(inst.cluster_dir_name, "Master")
        info = sp.loaded_mods.get(f"workshop-{WID}")
        assert info and info["status"] == "loaded", f"未检测到 MOD 加载:{sp.loaded_mods}"
        assert info["name"] == "Demo Mod" and info["version"] == "1.0.0", info
        print(f"[1] 已加载检测:{info['name']} v{info['version']} status={info['status']}  OK")

        # 2) 初始状态 unchecked
        m = svc.get_mods(db, inst.id)[0]
        assert m.update_status == "unchecked", m.update_status
        print("[2] 初始 update_status=unchecked  OK")

        # 3) 检查更新(time_updated=1000)→ 有 workshop 时间但无基线 → unknown
        modupdate.check_updates(db, inst.id)
        m = svc.get_mods(db, inst.id)[0]
        assert m.workshop_time_updated == 1000 and m.update_status == "unknown", \
            (m.workshop_time_updated, m.update_status)
        print("[3] check_updates 回填,无基线 → unknown  OK")

        # 4) 更新成功 → 对齐基线 → latest
        modupdate.mark_all_installed_current(db, settings)
        m = svc.get_mods(db, inst.id)[0]
        assert m.installed_time_updated == 1000 and m.update_status == "latest", \
            (m.installed_time_updated, m.update_status)
        print("[4] 更新后对齐基线 → latest  OK")

        # 5) 作者发新版(time_updated=2000)→ 再检查 → outdated
        fake_time["v"] = 2000
        modupdate.check_updates(db, inst.id)
        m = svc.get_mods(db, inst.id)[0]
        assert m.update_status == "outdated", m.update_status
        print("[5] 作者更新后 → outdated(有更新)  OK")

        # 6) 再次更新 → 回到 latest
        modupdate.mark_all_installed_current(db, settings)
        assert svc.get_mods(db, inst.id)[0].update_status == "latest"
        print("[6] 再次更新 → latest  OK")

        svc.stop_instance(db, sup, inst)
        print("\n✅ modupdate/loaded smoke PASSED")
    except AssertionError as exc:
        ok = False
        print(f"\n❌ FAILED: {exc}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
