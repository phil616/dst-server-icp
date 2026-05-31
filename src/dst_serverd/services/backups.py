"""文件级备份/还原(见 DESIGN.md 2.6 / 3.4)。

打包整个 clusters/<cluster>/ 目录(配置 + save)。还原前应先停服。
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from ..config import Settings
from ..db import Database
from ..models import Instance

log = logging.getLogger("dst_serverd.backups")


def _backups_dir(settings: Settings) -> Path:
    d = settings.base / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULT_RETENTION = 10


def _retention(db: Database) -> int:
    try:
        return max(1, int(db.get_kv("backup_retention", str(DEFAULT_RETENTION))))
    except ValueError:
        return DEFAULT_RETENTION


def backup_instance(
    db: Database, settings: Settings, inst: Instance, note: str = "", trigger: str = "manual"
) -> dict:
    cluster = inst.cluster_dir_name
    cdir = settings.cluster_dir(cluster)
    if not cdir.exists():
        raise FileNotFoundError(f"Cluster 目录不存在:{cdir}")
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = _backups_dir(settings) / f"{cluster}-{ts}-{trigger}.tar.gz"
    log.info("💾 备份实例 cluster=%s(%s)→ %s", cluster, trigger, out)
    # -C clusters_dir <cluster>:打进相对路径,便于原位还原
    subprocess.run(  # noqa: S603
        ["tar", "-czf", str(out), "-C", str(settings.clusters_dir), cluster],
        check=True,
    )
    size = out.stat().st_size
    log.info("  备份完成 %.1f KB → %s", size / 1024, out.name)
    bid = db.execute(
        "INSERT INTO backups (instance_id, type, trigger, path, size, created_at, note) "
        "VALUES (?, 'file', ?, ?, ?, ?, ?)",
        (inst.id, trigger, str(out), size, time.time(), note),
    )
    removed = prune_backups(db, settings, inst.id, _retention(db))
    if removed:
        log.info("  滚动清理旧备份 %d 份(保留最近 %d 份)", removed, _retention(db))
    return {"id": bid, "path": str(out), "size": size, "note": note, "trigger": trigger}


def list_backups(db: Database, instance_id: int) -> list[dict]:
    rows = db.query(
        "SELECT * FROM backups WHERE instance_id = ? ORDER BY created_at DESC",
        (instance_id,),
    )
    return [dict(r) for r in rows]


def restore_backup(db: Database, settings: Settings, backup_id: int) -> dict:
    """还原:把备份覆盖回 clusters/<cluster>/。调用方须先停服,还原后再启服。"""
    r = db.query_one("SELECT * FROM backups WHERE id = ?", (backup_id,))
    if r is None:
        raise FileNotFoundError(f"备份 {backup_id} 不存在")
    archive = Path(r["path"])
    if not archive.exists():
        raise FileNotFoundError(f"备份文件丢失:{archive}")
    subprocess.run(  # noqa: S603
        ["tar", "-xzf", str(archive), "-C", str(settings.clusters_dir)],
        check=True,
    )
    return {"restored_from": str(archive), "instance_id": r["instance_id"]}


def delete_backup(db: Database, backup_id: int) -> None:
    r = db.query_one("SELECT * FROM backups WHERE id = ?", (backup_id,))
    if r is None:
        return
    try:
        Path(r["path"]).unlink(missing_ok=True)
    except OSError:
        pass
    db.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
    log.info("🗑 删除备份 #%s", backup_id)


def prune_backups(db: Database, settings: Settings, instance_id: int, keep: int) -> int:
    """滚动清理:每实例保留最近 keep 份。返回删除数量。"""
    rows = db.query(
        "SELECT * FROM backups WHERE instance_id = ? ORDER BY created_at DESC",
        (instance_id,),
    )
    removed = 0
    for r in rows[keep:]:
        try:
            Path(r["path"]).unlink(missing_ok=True)
        except OSError:
            pass
        db.execute("DELETE FROM backups WHERE id = ?", (r["id"],))
        removed += 1
    return removed
