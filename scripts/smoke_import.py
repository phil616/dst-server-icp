#!/usr/bin/env python3
"""导入外界存档 冒烟测试(不经 HTTP)。

构造一个含 cluster.ini / Master+Caves(server.ini + save/session)/ adminlist / modoverrides
的 Cluster 压缩包,导入后验证:新实例入库、端口重新分配、**存档被保留**、访问/MOD 导入、
配置重渲染为新端口。最后用伪 DST 启动确认能续上存档世界(不重新生成)。

运行:  uv run python scripts/smoke_import.py
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dst_serverd.config import Settings  # noqa: E402
from dst_serverd.db import Database  # noqa: E402
from dst_serverd.parse import parse_ini_file  # noqa: E402
from dst_serverd.services import importer, instances as svc  # noqa: E402
from dst_serverd.supervisor import Supervisor  # noqa: E402
from dst_serverd.supervisor.process import ShardState  # noqa: E402

HERE = Path(__file__).resolve().parent


def make_archive(dst: Path) -> Path:
    """造一个外界 Cluster 存档压缩包。"""
    work = Path(tempfile.mkdtemp(prefix="ext-cluster-"))
    cl = work / "OldCluster"
    (cl / "Master" / "save" / "session" / "DEADBEEF01").mkdir(parents=True)
    (cl / "Caves" / "save" / "session" / "DEADBEEF02").mkdir(parents=True)
    (cl / "cluster.ini").write_text(
        "[NETWORK]\ncluster_name = Imported World\ncluster_description = from backup\n"
        "offline_cluster = true\ntick_rate = 15\n"
        "[GAMEPLAY]\ngame_mode = endless\nmax_players = 10\npvp = true\n"
        "[MISC]\nmax_snapshots = 8\n"
        "[SHARD]\ncluster_key = oldsecret123\nmaster_port = 10888\n", encoding="utf-8")
    # Master 端口与已存在实例冲突(10998)→ 导入时应重新分配;Caves 用空闲原端口 → 应保留
    (cl / "Master" / "server.ini").write_text(
        "[NETWORK]\nserver_port = 10998\n[SHARD]\nis_master = true\nname = Master\n"
        "[STEAM]\nmaster_server_port = 27018\nauthentication_port = 8768\n"
        "[ACCOUNT]\nencode_user_path = true\n", encoding="utf-8")
    (cl / "Caves" / "server.ini").write_text(
        "[NETWORK]\nserver_port = 12001\n[SHARD]\nis_master = false\nname = Caves\nid = 935042915\n"
        "shard_enabled = true\n[STEAM]\nmaster_server_port = 27019\nauthentication_port = 8769\n",
        encoding="utf-8")
    (cl / "Master" / "worldgenoverride.lua").write_text(
        'return {\n  override_enabled = true,\n  preset = "SURVIVAL_TOGETHER_CLASSIC",\n}\n')
    (cl / "Caves" / "worldgenoverride.lua").write_text(
        'return {\n  override_enabled = true,\n  preset = "DST_CAVE",\n}\n')
    (cl / "Master" / "modoverrides.lua").write_text(
        'return {\n  ["workshop-378160973"] = { enabled = true },\n}\n')
    (cl / "Caves" / "modoverrides.lua").write_text('return {}\n')
    (cl / "adminlist.txt").write_text("KU_owner001\n")
    # 标记文件,用于验证存档被保留
    (cl / "Master" / "save" / "session" / "DEADBEEF01" / "0000000005").write_bytes(b"world" * 500)

    with tarfile.open(dst, "w:gz") as tf:
        tf.add(cl, arcname="OldCluster")
    shutil.rmtree(work, ignore_errors=True)
    return dst


def main() -> int:  # noqa: C901
    base = Path(tempfile.mkdtemp(prefix="dstd-import-"))
    ok = True
    try:
        # 安装根 + 伪 DST(用于启动验证)
        bin_dir = base / "server" / "bin64"
        bin_dir.mkdir(parents=True)
        fake = bin_dir / "dontstarve_dedicated_server_nullrenderer_x64"
        shutil.copy(HERE / "fake_dst.py", fake)
        fake.chmod(0o755)
        (base / "clusters").mkdir()

        settings = Settings(base=base, conf_dir="clusters", shutdown_grace=4, sigterm_grace=2)
        settings.db = base / "db.sqlite3"
        db = Database(settings.db)

        # 先占一个实例,确保导入会重新分配端口(避免与已有冲突)
        svc.create_instance(db, settings, name="Existing", online=False, caves=True)

        archive = make_archive(base / "ext.tar.gz")
        inst = importer.import_archive(db, settings, archive, name_override="")
        cdir = settings.cluster_dir(inst.cluster_dir_name)
        print(f"[1] 导入实例 #{inst.id} cluster={inst.cluster_dir_name}  OK")

        # 元信息解析正确
        assert inst.name == "Imported World" and inst.game_mode == "endless"
        assert inst.max_players == 10 and inst.pvp and inst.max_snapshots == 8
        assert not inst.online  # offline_cluster=true 且无 token
        print("[2] 元信息解析(名称/模式/人数/PVP/快照/离线)  OK")

        # 端口重新分配(与已存在实例不冲突),且落盘 server.ini 为新端口
        shards = svc.get_shards(db, inst.id)
        master = next(s for s in shards if s.is_master)
        caves = next(s for s in shards if not s.is_master)
        assert master.server_port != 10998, "与已有实例冲突的端口应重新分配"
        assert 10998 <= master.server_port <= 11018, "重分配端口应在 LAN 范围"
        assert caves.server_port == 12001, "空闲的原端口应被保留(不破坏防火墙规则)"
        assert inst.master_port == 10888, "master_port 应保留原值"
        si = parse_ini_file(cdir / "Master" / "server.ini")
        assert si["NETWORK"]["server_port"] == str(master.server_port)
        # 关键字段保留:[ACCOUNT] encode_user_path、Secondary id
        assert si["ACCOUNT"]["encode_user_path"] == "true", "[ACCOUNT] 应被保留"
        assert parse_ini_file(cdir / "Caves" / "server.ini")["SHARD"]["id"] == "935042915", "Secondary id 应被保留"
        print(f"[3] 端口:Master {master.server_port}(原10998冲突→重分配)/ Caves {caves.server_port}(保留);关键字段保留  OK")

        # 存档被保留(关键!)
        kept = cdir / "Master" / "save" / "session" / "DEADBEEF01" / "0000000005"
        assert kept.exists() and kept.stat().st_size > 0, "存档应被保留"
        assert (cdir / "Caves" / "save" / "session" / "DEADBEEF02").exists()
        # worldgenoverride 原样保留(未被覆盖为默认)
        assert "SURVIVAL_TOGETHER_CLASSIC" in (cdir / "Master" / "worldgenoverride.lua").read_text()
        print("[4] 存档 save/ 与 worldgenoverride 原样保留  OK")

        # 访问控制 + MOD 导入 DB
        access = svc.get_access(db, inst.id)
        assert any(a.klei_id == "KU_owner001" and a.kind == "admin" for a in access)
        mods = svc.get_mods(db, inst.id)
        assert any(m.workshop_id == "378160973" for m in mods)
        assert (cdir / "adminlist.txt").read_text().strip() == "KU_owner001"
        print("[5] 访问控制 + MOD 导入并渲染  OK")

        # 启动:存档存在 → 续世界(伪 DST 仅验证拉起就绪)
        sup = Supervisor(settings, poll_interval=0.5)
        svc.start_instance(db, settings, sup, inst)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            sup.poll_once()
            sp = sup.get(inst.cluster_dir_name, "Master")
            if sp and sp.state == ShardState.READY:
                break
            time.sleep(0.2)
        assert sup.get(inst.cluster_dir_name, "Master").state == ShardState.READY
        # 启动不应破坏存档
        assert kept.exists(), "启动后存档仍应存在"
        svc.stop_instance(db, sup, inst)
        print("[6] 从导入存档启动就绪,存档未被破坏  OK")

        print("\n✅ import smoke PASSED")
    except AssertionError as exc:
        ok = False
        print(f"\n❌ FAILED: {exc}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
