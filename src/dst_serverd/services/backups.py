"""文件级备份/还原(见 DESIGN.md 2.6 / 3.4)。

打包整个 clusters/<cluster>/ 目录(配置 + save)。还原前应先停服。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import Settings
from ..db import Database
from ..models import Instance

if TYPE_CHECKING:
    from ..supervisor import Supervisor

log = logging.getLogger("dst_serverd.backups")

# 备份前强制存盘后,等待落盘的上限(秒)。大世界保存较慢,留足余量;超时则尽力而为。
SAVE_FLUSH_TIMEOUT = 30.0
# 判定"写入已静默"所需的连续无新写入时长(秒):世界快照(c_save 后约 1s 才真正写)与
# 玩家存档分多次写,需等其全部写完再打包。
SAVE_QUIESCE_SECONDS = 2.5

# 先把"在场玩家"的背包/角色逐个落盘,再存世界。源码实证(consolecommands.lua / autosaver.lua):
# c_save()→ms_save 只调度 ShardGameIndex:SaveCurrent() 存"世界",并不序列化在线玩家;
# 玩家档案要靠 SerializeUserSession() 在离场/优雅关服(c_shutdown 会先 OnDespawn 全员)/每日
# 自动存档时才写盘。故备份运行中的服务器若只发 c_save(),会丢在线玩家的背包/角色。
# SerializeUserSession 是全局函数,正常游戏中被频繁调用,对在场玩家调用安全(不会踢人/重生)。
_SAVE_PLAYERS_LUA = (
    "for i,v in ipairs(AllPlayers) do "
    "if v ~= nil and v.userid ~= nil then SerializeUserSession(v) end end"
)


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


def _newest_save_mtime(save_roots: list[Path]) -> float:
    """这些 save/ 目录树里最新文件的 mtime(无文件则 0)。用于探测"新快照是否已落盘"。"""
    best = 0.0
    for root in save_roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            try:
                if p.is_file():
                    best = max(best, p.stat().st_mtime)
            except OSError:
                pass
    return best


def flush_live_save(
    sup: Supervisor, settings: Settings, db: Database, inst: Instance,
    timeout: float = SAVE_FLUSH_TIMEOUT,
) -> bool:
    """备份前的写同步:对每个**运行中**的 Shard 先序列化在场玩家、再存世界,并等写入静默。

    关键(已对 DST 源码核实):
    - 世界状态常驻内存,save/session/<id>/ 只在 每日自动存档 / c_save() / 优雅关服 时刷新;
    - 且 c_save()(ms_save)在专服只存"世界",**不序列化在线玩家**;玩家的背包/角色靠
      SerializeUserSession() 在离场、优雅关服(c_shutdown 先 OnDespawn 全员)、每日自动存档时写盘。
    所以备份运行中的服务器必须**显式序列化在场玩家 + 存世界**,否则还原后世界在、玩家进度全丢。
    返回是否确认有写入落盘。服务器已停时无需处理(优雅停服已存过,磁盘即权威)。
    """
    cluster = inst.cluster_dir_name
    rows = db.query("SELECT shard_dir_name FROM shards WHERE instance_id = ?", (inst.id,))
    running = [r["shard_dir_name"] for r in rows
               if (p := sup.get(cluster, r["shard_dir_name"])) is not None and p.is_alive()]
    if not running:
        return False

    save_roots = [settings.cluster_dir(cluster) / s / "save" for s in running]
    before = _newest_save_mtime(save_roots)
    sent = 0
    for s in running:
        sup.send(cluster, s, _SAVE_PLAYERS_LUA)  # ① 在场玩家背包/角色落盘
        if sup.send(cluster, s, "c_save()"):     # ② 世界快照落盘
            sent += 1
    log.info("💾 备份前写同步:%d 个运行中 Shard 已序列化在场玩家并 c_save()", sent)
    if not sent:
        return False

    # 等"保存开始"再等"写入静默":玩家档案先写、世界快照 c_save 后约 1s 才写且大世界更久,
    # 必须等所有写入停下来再打包,避免抓到只写了一半的存档。
    deadline = time.monotonic() + timeout
    started = False
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if _newest_save_mtime(save_roots) > before:
            started = True
            break
    if not started:
        log.warning("  ⚠ 等待存盘开始超时(%.0fs);仍按当前磁盘内容备份", timeout)
        return False

    last_mtime = _newest_save_mtime(save_roots)
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.5)
        m = _newest_save_mtime(save_roots)
        if m > last_mtime:
            last_mtime, last_change = m, time.monotonic()
        elif time.monotonic() - last_change >= SAVE_QUIESCE_SECONDS:
            log.info("  ✅ 世界快照与在场玩家存档均已落盘,开始打包")
            return True
    log.warning("  ⚠ 存盘等待达上限(%.0fs);按当前磁盘内容备份", timeout)
    return True


def backup_instance(
    db: Database, settings: Settings, inst: Instance, note: str = "", trigger: str = "manual",
    sup: Supervisor | None = None,
) -> dict:
    cluster = inst.cluster_dir_name
    cdir = settings.cluster_dir(cluster)
    if not cdir.exists():
        raise FileNotFoundError(f"Cluster 目录不存在:{cdir}")
    # 写同步:服务器在跑就先强制存盘并等落盘,确保归档含最新进度(否则可能只存到初始世界)
    if sup is not None:
        flush_live_save(sup, settings, db, inst)
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


def _archive_top_dir(archive: Path) -> str | None:
    """读归档顶层目录名(= 打包时的 <cluster>),用于兜底定位还原目标。"""
    out = subprocess.run(  # noqa: S603
        ["tar", "-tzf", str(archive)], capture_output=True, text=True, check=True)
    for line in out.stdout.splitlines():
        name = line.strip().lstrip("./")
        if name:
            return name.split("/", 1)[0]
    return None


def restore_backup(db: Database, settings: Settings, backup_id: int) -> dict:
    """还原:用备份**整体替换** clusters/<cluster>/。调用方须先停服,还原后再启服。

    关键:必须先清空旧目录再落地,不能用 `tar -x` 直接覆盖。DST 每次保存都在
    `<Shard>/save/session/<id>/` 追加一个编号更大的快照,启动时**只加载最新快照**;
    若沿用旧的合并式解包,备份后新写入的快照会残留,导致每次"还原"实际仍是最新存档
    (即本 BUG:无法回滚)。这里解包到临时暂存目录,成功后再原子替换,失败则原目录无损。
    """
    r = db.query_one("SELECT * FROM backups WHERE id = ?", (backup_id,))
    if r is None:
        raise FileNotFoundError(f"备份 {backup_id} 不存在")
    archive = Path(r["path"])
    if not archive.exists():
        raise FileNotFoundError(f"备份文件丢失:{archive}")

    # 确定要被替换的 cluster 目录:优先实例配置,兜底取归档顶层目录名
    row = db.query_one(
        "SELECT cluster_dir_name FROM server_instances WHERE id = ?", (r["instance_id"],))
    cluster = row["cluster_dir_name"] if row else _archive_top_dir(archive)
    if not cluster:
        raise FileNotFoundError("无法确定备份对应的 cluster 目录")

    clusters_dir = settings.clusters_dir
    clusters_dir.mkdir(parents=True, exist_ok=True)
    target = clusters_dir / cluster

    # 解包到同盘临时目录(rename 才是原子的);成功后再删旧目录并就位
    staging = Path(tempfile.mkdtemp(dir=clusters_dir, prefix=f".restore-{cluster}-"))
    try:
        subprocess.run(  # noqa: S603
            ["tar", "-xzf", str(archive), "-C", str(staging)], check=True)
        extracted = staging / cluster
        if not extracted.is_dir():  # 归档顶层名与库里 cluster 名不一致时兜底
            subdirs = [p for p in staging.iterdir() if p.is_dir()]
            if len(subdirs) != 1:
                raise FileNotFoundError(f"备份归档结构异常,无法定位 cluster 目录:{archive}")
            extracted = subdirs[0]
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(extracted), str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    log.info("♻ 已用备份整体替换 cluster=%s ← %s", cluster, archive.name)
    return {"restored_from": str(archive), "instance_id": r["instance_id"], "cluster": cluster}


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
