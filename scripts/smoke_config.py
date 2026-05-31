#!/usr/bin/env python3
"""配置/访问控制/存档/备份 体系的服务层冒烟测试(不经 HTTP)。

覆盖:配置更新→渲染回 cluster.ini、whitelist_slots 校验、在线服需 token 校验、
访问控制三表渲染 + 解析读回、存档信息自省、备份 trigger + 保留份数滚动清理 + 删除。

运行:  uv run python scripts/smoke_config.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dst_serverd.config import Settings  # noqa: E402
from dst_serverd.db import Database  # noqa: E402
from dst_serverd.parse import read_cluster_config  # noqa: E402
from dst_serverd.services import backups as bk  # noqa: E402
from dst_serverd.services import instances as svc  # noqa: E402
from dst_serverd.services import save as save_svc  # noqa: E402


def expect_error(fn, msg):
    try:
        fn()
    except svc.InstanceError:
        return
    raise AssertionError(f"应当抛 InstanceError:{msg}")


def main() -> int:  # noqa: C901
    base = Path(tempfile.mkdtemp(prefix="dstd-cfg-"))
    ok = True
    try:
        settings = Settings(base=base, conf_dir="clusters")
        settings.db = base / "db.sqlite3"
        db = Database(settings.db)

        inst = svc.create_instance(db, settings, name="Cfg Test", online=False, caves=True)
        cdir = settings.cluster_dir(inst.cluster_dir_name)
        print(f"[1] 创建实例 #{inst.id} ({inst.cluster_dir_name})  OK")

        # 2) 配置更新 → 渲染回 cluster.ini
        inst = svc.update_instance(db, settings, inst, {
            "max_players": 8, "whitelist_slots": 2, "tick_rate": 30, "pvp": True,
            "autosaver_enabled": False, "vote_enabled": False, "lan_only_cluster": True,
            "cluster_description": "hello world",
        })
        cini = (cdir / "cluster.ini").read_text()
        for needle in ["max_players = 8", "whitelist_slots = 2", "tick_rate = 30",
                       "pvp = true", "autosaver_enabled = false", "vote_enabled = false",
                       "lan_only_cluster = true", "cluster_description = hello world"]:
            assert needle in cini, f"cluster.ini 缺少 {needle!r}\n{cini}"
        print("[2] 配置更新渲染回 cluster.ini  OK")

        # 3) 校验:whitelist_slots>max_players、在线服需 token
        expect_error(lambda: svc.update_instance(db, settings, inst, {"whitelist_slots": 99}),
                     "whitelist_slots>max_players")
        expect_error(lambda: svc.update_instance(db, settings, inst, {"online": True, "token": ""}),
                     "在线服无 token")
        print("[3] 配置校验(slots/token)  OK")

        # 4) 访问控制三表渲染 + 解析读回
        svc.add_access(db, settings, inst, "admin", "KU_admin123", "我")
        svc.add_access(db, settings, inst, "whitelist", "KU_white111")
        svc.add_access(db, settings, inst, "blocklist", "OU_000111222")
        assert (cdir / "adminlist.txt").read_text().strip() == "KU_admin123"
        assert "KU_white111" in (cdir / "whitelist.txt").read_text()
        assert "OU_000111222" in (cdir / "blocklist.txt").read_text()
        expect_error(lambda: svc.add_access(db, settings, inst, "admin", "bad-id"), "非法 ID")
        print("[4] 访问控制三表渲染 + 非法 ID 校验  OK")

        parsed = read_cluster_config(settings, inst.cluster_dir_name)
        assert parsed["cluster_ini"]["GAMEPLAY"]["max_players"] == "8"
        assert parsed["adminlist"] == ["KU_admin123"]
        assert parsed["shards"]["Master"]["server_ini"]["SHARD"]["is_master"] == "true"
        print("[5] 解析落盘配置(cluster.ini / server.ini / 列表)读回  OK")

        # 6) 移除 admin → adminlist.txt 应被删除(无条目)
        svc.remove_access(db, settings, inst, "admin", "KU_admin123")
        assert not (cdir / "adminlist.txt").exists(), "空 adminlist 应删除文件"
        print("[6] 移除访问条目 → 空列表文件删除  OK")

        # 7) 存档信息自省(伪造一个 session)
        sess = cdir / "Master" / "save" / "session" / "ABCDEF0123"
        sess.mkdir(parents=True)
        (sess / "0000000001").write_bytes(b"x" * 2048)
        info = save_svc.shard_save_info(settings, inst.cluster_dir_name, "Master")
        assert info["exists"] and info["size"] >= 2048 and len(info["sessions"]) == 1
        assert info["sessions"][0]["session_id"] == "ABCDEF0123"
        print(f"[7] 存档自省:size={info['size']} sessions={len(info['sessions'])}  OK")

        # 8) 备份 trigger + 保留份数滚动清理 + 删除
        db.set_kv("backup_retention", "2")
        for i in range(3):
            bk.backup_instance(db, settings, inst, note=f"b{i}", trigger="manual")
        kept = bk.list_backups(db, inst.id)
        assert len(kept) == 2, f"应保留 2 份,实际 {len(kept)}"
        assert all("trigger" in r for r in kept)
        bk.delete_backup(db, kept[0]["id"])
        assert len(bk.list_backups(db, inst.id)) == 1
        print("[8] 备份 trigger + 保留 2 份滚动清理 + 删除  OK")

        print("\n✅ config/access/save/backup smoke PASSED")
    except AssertionError as exc:
        ok = False
        print(f"\n❌ FAILED: {exc}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
