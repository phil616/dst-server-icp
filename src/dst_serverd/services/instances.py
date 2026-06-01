"""实例(Cluster)编排:CRUD + 配置渲染 + 启停(见 DESIGN.md 2.3 / 2.4 / 3.4)。

DB 是"有哪些实例及其配置"的权威;supervisor 的 spec.json 是"进程怎么重启"的句柄,
由本服务在启动 Shard 时一并写出,从而 reconcile 与 DB 保持一致。
"""

from __future__ import annotations

import logging
import re
import secrets
import shutil
import time

from ..config import Settings
from ..db import Database
from ..models import AccessEntry, Instance, Mod, Shard
from ..ports import (
    allocate_master_port,
    allocate_shard_ports,
    is_port_free,
    used_ports,
)
from ..render import write_instance_files
from ..supervisor import Supervisor

log = logging.getLogger("dst_serverd.instances")

GAME_MODES = {"survival", "endless", "wilderness"}
INTENTIONS = {"cooperative", "competitive", "social", "madness"}
ACCESS_KINDS = {"admin", "whitelist", "blocklist"}
KLEI_ID_RE = re.compile(r"^(KU|OU)_[A-Za-z0-9_-]{4,}$")
MASTER_PRESET = "SURVIVAL_TOGETHER"
CAVES_PRESET = "DST_CAVE"
# 可经 PATCH 更新的房间/元信息/玩法/网络字段
EDITABLE_FIELDS = {
    "name", "cluster_description", "cluster_password", "cluster_intention",
    "game_mode", "max_players", "pvp", "pause_when_empty", "max_snapshots",
    "tick_rate", "vote_enabled", "autosaver_enabled", "whitelist_slots",
    "lan_only_cluster", "online", "token",
}


class InstanceError(ValueError):
    pass


# ---------- 读 ----------
def get_instance(db: Database, instance_id: int) -> Instance | None:
    r = db.query_one("SELECT * FROM server_instances WHERE id = ?", (instance_id,))
    return Instance.from_row(r) if r else None


def get_instance_by_cluster(db: Database, cluster: str) -> Instance | None:
    r = db.query_one(
        "SELECT * FROM server_instances WHERE cluster_dir_name = ?", (cluster,)
    )
    return Instance.from_row(r) if r else None


def list_instances(db: Database) -> list[Instance]:
    return [Instance.from_row(r) for r in db.query(
        "SELECT * FROM server_instances ORDER BY id"
    )]


def get_shards(db: Database, instance_id: int) -> list[Shard]:
    rows = db.query(
        "SELECT * FROM shards WHERE instance_id = ? ORDER BY is_master DESC, id",
        (instance_id,),
    )
    return [Shard.from_row(r) for r in rows]


def get_shard(db: Database, instance_id: int, shard_dir_name: str) -> Shard | None:
    r = db.query_one(
        "SELECT * FROM shards WHERE instance_id = ? AND shard_dir_name = ?",
        (instance_id, shard_dir_name),
    )
    return Shard.from_row(r) if r else None


def get_mods(db: Database, instance_id: int) -> list[Mod]:
    rows = db.query("SELECT * FROM mods WHERE instance_id = ? ORDER BY id", (instance_id,))
    return [Mod.from_row(r) for r in rows]


def get_access(db: Database, instance_id: int, kind: str | None = None) -> list[AccessEntry]:
    if kind:
        rows = db.query(
            "SELECT * FROM access_entries WHERE instance_id = ? AND kind = ? ORDER BY id",
            (instance_id, kind))
    else:
        rows = db.query(
            "SELECT * FROM access_entries WHERE instance_id = ? ORDER BY kind, id", (instance_id,))
    return [AccessEntry.from_row(r) for r in rows]


# ---------- 创建 ----------
def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    return s or "Cluster"


def _unique_cluster_dir(db: Database, name: str) -> str:
    base = _slug(name)
    candidate = base
    n = 1
    while db.query_one(
        "SELECT 1 FROM server_instances WHERE cluster_dir_name = ?", (candidate,)
    ):
        n += 1
        candidate = f"{base}_{n}"
    return candidate


def create_instance(
    db: Database,
    settings: Settings,
    *,
    name: str,
    online: bool = True,
    token: str = "",
    game_mode: str = "survival",
    pvp: bool = False,
    max_players: int = 6,
    max_snapshots: int = 6,
    pause_when_empty: bool = True,
    cluster_password: str = "",
    cluster_intention: str = "cooperative",
    cluster_description: str = "",
    caves: bool = True,
) -> Instance:
    if game_mode not in GAME_MODES:
        raise InstanceError(f"game_mode 非法:{game_mode}")
    if cluster_intention not in INTENTIONS:
        raise InstanceError(f"cluster_intention 非法:{cluster_intention}")
    if online and not token.strip():
        raise InstanceError("在线服必须提供 cluster_token(见 DESIGN.md 3.1#2)")

    cluster_dir = _unique_cluster_dir(db, name)
    cluster_key = secrets.token_hex(12)
    master_port = allocate_master_port(db)

    inst_id = db.execute(
        "INSERT INTO server_instances (name, cluster_dir_name, online, game_mode, pvp, "
        "max_players, max_snapshots, pause_when_empty, cluster_password, cluster_intention, "
        "cluster_description, cluster_key, master_port, token, created_at, desired_status, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'stopped','created')",
        (
            name, cluster_dir, int(online), game_mode, int(pvp), max_players, max_snapshots,
            int(pause_when_empty), cluster_password, cluster_intention, cluster_description,
            cluster_key, master_port, token.strip(), time.time(),
        ),
    )

    n_shards = 2 if caves else 1
    ports = allocate_shard_ports(db, n_shards)
    # Master
    sp, msp, ap = ports[0]
    db.execute(
        "INSERT INTO shards (instance_id, role, shard_dir_name, is_master, server_port, "
        "master_server_port, authentication_port, worldgen_preset) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (inst_id, "master", "Master", 1, sp, msp, ap, MASTER_PRESET),
    )
    if caves:
        sp, msp, ap = ports[1]
        db.execute(
            "INSERT INTO shards (instance_id, role, shard_dir_name, is_master, server_port, "
            "master_server_port, authentication_port, worldgen_preset) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (inst_id, "secondary", "Caves", 0, sp, msp, ap, CAVES_PRESET),
        )

    inst = get_instance(db, inst_id)
    assert inst is not None
    shards = get_shards(db, inst.id)
    log.info(
        "✚ 创建实例 #%s name=%r cluster=%s 模式=%s %s 人数=%s shards=%s master_port=%s",
        inst.id, inst.name, inst.cluster_dir_name, inst.game_mode,
        "在线" if inst.online else "离线", inst.max_players,
        [f"{s.shard_dir_name}:{s.server_port}" for s in shards], inst.master_port,
    )
    rerender(db, settings, inst)
    log.info("  已渲染配置到 %s", settings.cluster_dir(inst.cluster_dir_name))
    return inst


# ---------- 渲染 ----------
def rerender(db: Database, settings: Settings, inst: Instance) -> None:
    shards = get_shards(db, inst.id)
    mods = get_mods(db, inst.id)
    access = get_access(db, inst.id)
    write_instance_files(settings, inst, shards, mods, access)


# ---------- 配置更新(房间/元信息/玩法/网络) ----------
def update_instance(db: Database, settings: Settings, inst: Instance, fields: dict) -> Instance:
    data = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v is not None}
    if not data:
        return inst
    # 校验
    if "game_mode" in data and data["game_mode"] not in GAME_MODES:
        raise InstanceError(f"game_mode 非法:{data['game_mode']}")
    if "cluster_intention" in data and data["cluster_intention"] not in INTENTIONS:
        raise InstanceError(f"cluster_intention 非法:{data['cluster_intention']}")
    max_players = data.get("max_players", inst.max_players)
    if "whitelist_slots" in data and data["whitelist_slots"] > max_players:
        raise InstanceError("whitelist_slots 不能大于 max_players")
    online = data.get("online", inst.online)
    token = data.get("token", inst.token)
    if online and not str(token).strip():
        raise InstanceError("在线服必须有 cluster_token")

    sets, params = [], []
    for k, v in data.items():
        sets.append(f"{k} = ?")
        params.append(int(v) if isinstance(v, bool) else v)
    params.append(inst.id)
    db.execute(f"UPDATE server_instances SET {', '.join(sets)} WHERE id = ?", params)
    updated = get_instance(db, inst.id)
    assert updated is not None
    rerender(db, settings, updated)
    log.info("✎ 更新实例 cluster=%s 字段=%s(多数需重启对应 Shard 生效)",
             inst.cluster_dir_name, sorted(data.keys()))
    return updated


# ---------- Shard 端口自定义(写回各自的 server.ini) ----------
def _validate_shard_ports(db: Database, shard: Shard, sp: int, msp: int, ap: int) -> None:
    """校验单个 Shard 的三端口:类型、范围、互不相同、与其它 Shard / Cluster master_port 不冲突。"""
    for label, val in (("server_port", sp), ("master_server_port", msp),
                       ("authentication_port", ap)):
        if not isinstance(val, int):
            raise InstanceError(f"{label} 必须为整数")
    if len({sp, msp, ap}) != 3:
        raise InstanceError("server_port / master_server_port / authentication_port 三者不能相同")
    if not (1024 <= sp <= 65535):
        raise InstanceError("server_port 必须在 1024–65535")
    if not (1024 <= msp <= 65535):
        raise InstanceError("master_server_port 必须在 1024–65535")
    if not (1024 <= ap <= 65535):
        raise InstanceError("authentication_port 必须在 1024–65535")

    # 同机各 Shard 必须不同(排除该 Shard 自身的旧值)
    if sp in used_ports(db, "server_port") - {shard.server_port}:
        raise InstanceError(f"server_port {sp} 已被其它 Shard 占用")
    if msp in used_ports(db, "master_server_port") - {shard.master_server_port}:
        raise InstanceError(f"master_server_port {msp} 已被其它 Shard 占用")
    if ap in used_ports(db, "authentication_port") - {shard.authentication_port}:
        raise InstanceError(f"authentication_port {ap} 已被其它 Shard 占用")

    # server_port 不能与任一 Cluster 的 master_port(Shard 间通信)冲突
    if sp in used_ports(db, "master_port", table="server_instances"):
        raise InstanceError(f"server_port {sp} 与某 Cluster 的 master_port 冲突,请换一个")

    # OS 层预检:仅检查发生变更的端口(未变更的端口正被本 Shard 自身占用,属正常)。
    # 捕获 DB 未跟踪的占用——外部程序或上次崩溃残留的僵尸进程,占用则拒绝本次修改。
    for label, new_val, old_val in (
        ("server_port", sp, shard.server_port),
        ("master_server_port", msp, shard.master_server_port),
        ("authentication_port", ap, shard.authentication_port),
    ):
        if new_val != old_val and not is_port_free(new_val):
            raise InstanceError(
                f"{label} 端口 {new_val} 已被系统占用(可能是其它程序或残留的僵尸进程),"
                "已拒绝本次修改,请改用其它端口或先释放该端口")


def update_shard_ports(
    db: Database, settings: Settings, inst: Instance, shard_dir_name: str, *,
    server_port: int | None = None,
    master_server_port: int | None = None,
    authentication_port: int | None = None,
) -> Shard:
    """自定义某个 Shard(Master / Caves)的端口并写回其 server.ini(重启该 Shard 后生效)。"""
    shard = get_shard(db, inst.id, shard_dir_name)
    if shard is None:
        raise InstanceError(f"Shard 不存在:{shard_dir_name}")

    sp = shard.server_port if server_port is None else server_port
    msp = shard.master_server_port if master_server_port is None else master_server_port
    ap = shard.authentication_port if authentication_port is None else authentication_port

    if (sp, msp, ap) == (shard.server_port, shard.master_server_port, shard.authentication_port):
        return shard  # 无变化

    _validate_shard_ports(db, shard, sp, msp, ap)
    db.execute(
        "UPDATE shards SET server_port=?, master_server_port=?, authentication_port=? WHERE id=?",
        (sp, msp, ap, shard.id),
    )
    rerender(db, settings, inst)
    log.info("✎ 更新 Shard 端口 cluster=%s shard=%s server_port=%s master_server_port=%s "
             "authentication_port=%s(需重启该 Shard 生效)",
             inst.cluster_dir_name, shard_dir_name, sp, msp, ap)
    updated = get_shard(db, inst.id, shard_dir_name)
    assert updated is not None
    return updated


# ---------- 访问控制(adminlist / whitelist / blocklist) ----------
def add_access(db: Database, settings: Settings, inst: Instance, kind: str,
               klei_id: str, note: str = "") -> AccessEntry:
    if kind not in ACCESS_KINDS:
        raise InstanceError(f"kind 非法:{kind}")
    klei_id = klei_id.strip()
    if not KLEI_ID_RE.match(klei_id):
        raise InstanceError(f"ID 格式非法(应为 KU_/OU_ 开头):{klei_id}")
    db.execute(
        "INSERT OR REPLACE INTO access_entries (id, instance_id, kind, klei_id, note) "
        "VALUES ((SELECT id FROM access_entries WHERE instance_id=? AND kind=? AND klei_id=?), "
        "?,?,?,?)",
        (inst.id, kind, klei_id, inst.id, kind, klei_id, note))
    rerender(db, settings, inst)
    log.info("＋ 访问控制 %s += %s(cluster=%s,重启后生效)", kind, klei_id, inst.cluster_dir_name)
    r = db.query_one(
        "SELECT * FROM access_entries WHERE instance_id=? AND kind=? AND klei_id=?",
        (inst.id, kind, klei_id))
    assert r is not None
    return AccessEntry.from_row(r)


def remove_access(db: Database, settings: Settings, inst: Instance, kind: str, klei_id: str) -> None:
    db.execute(
        "DELETE FROM access_entries WHERE instance_id=? AND kind=? AND klei_id=?",
        (inst.id, kind, klei_id))
    rerender(db, settings, inst)
    log.info("－ 访问控制 %s -= %s(cluster=%s)", kind, klei_id, inst.cluster_dir_name)


# ---------- 启停 ----------
def start_instance(db: Database, settings: Settings, sup: Supervisor, inst: Instance) -> None:
    log.info("▶ 启动实例 cluster=%s", inst.cluster_dir_name)
    rerender(db, settings, inst)  # 启动前确保配置最新
    db.execute(
        "UPDATE server_instances SET desired_status='running', status='starting' WHERE id=?",
        (inst.id,),
    )
    # Master 先于 Secondary(get_shards 已按 is_master DESC 排序)
    for shard in get_shards(db, inst.id):
        log.info("  → 启动 Shard %s (port %s)", shard.shard_dir_name, shard.server_port)
        spec = sup.build_spec(inst.cluster_dir_name, shard.shard_dir_name)
        sp = sup.start(spec)
        log.info("    Shard %s 已拉起 pid=%s,等待就绪(Sim paused)…", shard.shard_dir_name, sp.pid)
    db.execute("UPDATE server_instances SET status='running' WHERE id=?", (inst.id,))


def stop_instance(
    db: Database, sup: Supervisor, inst: Instance, *, save: bool = True, force: bool = False
) -> None:
    mode = "强制" if force else "优雅"
    log.info("■ %s停止实例 cluster=%s(save=%s)", mode, inst.cluster_dir_name, save and not force)
    db.execute("UPDATE server_instances SET desired_status='stopped' WHERE id=?", (inst.id,))
    # 逐个停;单个 Shard 失败不得中断其余(此前 Master 异常会导致 Caves 漏停)
    for shard in get_shards(db, inst.id):
        log.info("  → %s关停 Shard %s …", mode, shard.shard_dir_name)
        try:
            sup.stop(inst.cluster_dir_name, shard.shard_dir_name, save=save, force=force)
        except Exception:  # noqa: BLE001 保证继续关停其余 Shard
            log.exception("关停 Shard %s 失败,继续处理其余 Shard", shard.shard_dir_name)
    # 兜底:系统层清掉该 cluster 任何残留进程(句柄丢失/僵尸进程占端口)
    killed = sup.kill_orphans(inst.cluster_dir_name)
    if killed:
        log.warning("  ⚠ 清理残留进程 %d 个 cluster=%s", killed, inst.cluster_dir_name)
    db.execute("UPDATE server_instances SET status='stopped' WHERE id=?", (inst.id,))


def delete_instance(db: Database, settings: Settings, sup: Supervisor, inst: Instance) -> None:
    log.info("✖ 删除实例 cluster=%s(将清除存档目录)", inst.cluster_dir_name)
    for shard in get_shards(db, inst.id):
        sup.remove(inst.cluster_dir_name, shard.shard_dir_name)
    shutil.rmtree(settings.cluster_dir(inst.cluster_dir_name), ignore_errors=True)
    db.execute("DELETE FROM server_instances WHERE id = ?", (inst.id,))  # 级联删 shards/mods/backups


# ---------- MOD ----------
def add_mod(
    db: Database, settings: Settings, inst: Instance, *,
    workshop_id: str, name: str = "", source: str = "workshop",
    enabled: bool = True, config: dict | None = None,
) -> Mod:
    import json

    db.execute(
        "INSERT OR REPLACE INTO mods (id, instance_id, workshop_id, name, enabled, source, config_json) "
        "VALUES ((SELECT id FROM mods WHERE instance_id=? AND workshop_id=?), ?,?,?,?,?,?)",
        (inst.id, workshop_id, inst.id, workshop_id, name, int(enabled), source,
         json.dumps(config or {})),
    )
    rerender(db, settings, inst)
    log.info("＋ MOD %s 加入 cluster=%s 并写回 modoverrides(重启对应 Shard 生效)",
             workshop_id, inst.cluster_dir_name)
    r = db.query_one(
        "SELECT * FROM mods WHERE instance_id=? AND workshop_id=?", (inst.id, workshop_id)
    )
    assert r is not None
    return Mod.from_row(r)


def remove_mod(db: Database, settings: Settings, inst: Instance, workshop_id: str) -> None:
    db.execute(
        "DELETE FROM mods WHERE instance_id=? AND workshop_id=?", (inst.id, workshop_id)
    )
    rerender(db, settings, inst)
    log.info("－ MOD %s 移出 cluster=%s 并写回 modoverrides", workshop_id, inst.cluster_dir_name)


def set_mod(
    db: Database, settings: Settings, inst: Instance, workshop_id: str, *,
    enabled: bool | None = None, config: dict | None = None,
) -> Mod:
    import json

    row = db.query_one(
        "SELECT * FROM mods WHERE instance_id=? AND workshop_id=?", (inst.id, workshop_id))
    if row is None:
        raise InstanceError(f"MOD {workshop_id} 不存在")
    new_enabled = row["enabled"] if enabled is None else int(enabled)
    new_config = row["config_json"] if config is None else json.dumps(config, ensure_ascii=False)
    db.execute(
        "UPDATE mods SET enabled=?, config_json=? WHERE instance_id=? AND workshop_id=?",
        (new_enabled, new_config, inst.id, workshop_id))
    rerender(db, settings, inst)
    log.info("✎ MOD %s 更新(enabled=%s)cluster=%s", workshop_id, bool(new_enabled),
             inst.cluster_dir_name)
    r = db.query_one(
        "SELECT * FROM mods WHERE instance_id=? AND workshop_id=?", (inst.id, workshop_id))
    assert r is not None
    return Mod.from_row(r)
