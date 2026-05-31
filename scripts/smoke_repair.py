#!/usr/bin/env python3
"""MOD 下载体系(重构后)冒烟测试。

验证基于 Klei 论坛/开源镜像实践的可靠做法:
1. 用 SteamCMD `workshop_download_item 322330 <id>` 下载,拷进 server/mods/workshop-<id>/(V1);
2. 覆盖 steamclient.so 到服务端 lib 目录(修游戏内下载器);
3. 子进程超时会被强制终止(避免卡死阻塞作业队列);
4. update_mods_job 端到端把 DB 里的 MOD 装进 server/mods/。

运行:  uv run python scripts/smoke_repair.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dst_serverd.config import Settings  # noqa: E402
from dst_serverd.db import Database  # noqa: E402
from dst_serverd.proxy import load_proxy  # noqa: E402
from dst_serverd.services import install, modupdate  # noqa: E402
from dst_serverd.services import instances as svc  # noqa: E402

# 伪 SteamCMD:支持 workshop_download_item(造出 MOD 内容)与 app_update;每次运行生成 steamclient.so
FAKE_STEAMCMD = r'''#!/usr/bin/env bash
SCDIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCDIR/linux64" "$SCDIR/linux32"
echo client64 > "$SCDIR/linux64/steamclient.so"
echo client32 > "$SCDIR/linux32/steamclient.so"
DIR=""; WID=""; mode=""; args=("$@"); i=0
while [ $i -lt ${#args[@]} ]; do
  case "${args[$i]}" in
    +force_install_dir) i=$((i+1)); DIR="${args[$i]}";;
    +workshop_download_item) mode=ws; i=$((i+2)); WID="${args[$i]}";;
    +app_update) mode=app;;
  esac
  i=$((i+1))
done
if [ "$mode" = ws ]; then
  CD="$DIR/steamapps/workshop/content/322330/$WID"; mkdir -p "$CD"
  echo "name=\"Fake$WID\"" > "$CD/modinfo.lua"; echo "-- mod" > "$CD/modmain.lua"
  echo "Success. Downloaded item $WID"
elif [ "$mode" = app ]; then
  mkdir -p "$DIR/steamapps" "$DIR/bin64"; echo "Success! App '343050' fully installed."
fi
exit 0
'''


def main() -> int:  # noqa: C901
    base = Path(tempfile.mkdtemp(prefix="dstd-repair-"))
    ok = True
    try:
        (base / "server" / "bin64").mkdir(parents=True)
        (base / "server" / "bin64" / "dontstarve_dedicated_server_nullrenderer_x64").write_text("#!/bin/sh\n")
        sc = base / "steamcmd"
        sc.mkdir()
        (sc / "steamcmd.sh").write_text(FAKE_STEAMCMD)
        (sc / "steamcmd.sh").chmod(0o755)
        (base / "clusters").mkdir()

        settings = Settings(base=base, conf_dir="clusters")
        settings.db = base / "db.sqlite3"
        db = Database(settings.db)
        proxy = load_proxy(db)

        # 1) 单个 MOD:SteamCMD 下载 → 拷进 server/mods/workshop-<id>/
        assert install.download_one_mod(settings, proxy, "1418746242")
        modinfo = base / "server" / "mods" / "workshop-1418746242" / "modinfo.lua"
        assert modinfo.exists(), "MOD 未落到 server/mods/workshop-<id>/"
        print("[1] SteamCMD workshop_download_item → mods/workshop-1418746242/  OK")

        # 2) steamclient.so 覆盖到服务端 lib 目录
        done = install.fix_steamclient(settings)
        assert (base / "server" / "bin64" / "lib64" / "steamclient.so").exists(), "未覆盖 lib64/steamclient.so"
        assert (base / "server" / "bin" / "lib32" / "steamclient.so").exists(), "未覆盖 lib32/steamclient.so"
        print(f"[2] 覆盖 steamclient.so({len(done)} 处)  OK")

        # 3) 子进程超时会被强制终止(不再卡死)
        res = install._run(settings, "sleep-test", ["sleep", "5"], timeout=1)
        assert res.returncode == 124 and "超时" in res.error_hint, (res.returncode, res.error_hint)
        print("[3] 子进程超时强制终止(rc=124)  OK")

        # 4) update_mods_job 端到端:DB 里的 MOD 全部装进 server/mods/
        inst = svc.create_instance(db, settings, name="Repair", online=False, caves=False)
        svc.add_mod(db, settings, inst, workshop_id="378160973", name="GP")
        svc.add_mod(db, settings, inst, workshop_id="2189004162", name="Insight")
        # mark_all_installed_current 会联网,打桩避免网络
        modupdate.fetch_workshop_details = lambda _db, ids, timeout=15: {
            w: {"time_updated": 100, "title": f"M{w}", "file_size": 1} for w in ids}
        r = modupdate.update_mods_job(db, settings)
        assert getattr(r, "ok", False), f"update_mods_job 失败:{getattr(r,'error_hint','')}"
        assert (base / "server" / "mods" / "workshop-378160973" / "modinfo.lua").exists()
        assert (base / "server" / "mods" / "workshop-2189004162" / "modinfo.lua").exists()
        print("[4] update_mods_job 端到端:2 个 MOD 装入 server/mods/  OK")

        print("\n✅ repair smoke PASSED")
    except AssertionError as exc:
        ok = False
        print(f"\n❌ FAILED: {exc}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
