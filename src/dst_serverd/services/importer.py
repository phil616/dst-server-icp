"""从外界存档导入实例 —— 上传一个 Cluster 压缩包,解析后注册为新实例并保留其世界。

要点:DST 在存档(save/)存在时**加载已有世界、不重新生成**。所以导入 = 解压 → 解析
cluster.ini/server.ini/列表/MOD → 重新分配端口与目录名 → 入库 → 落到 clusters/<新名>/,
**保留 save/、worldgenoverride、modoverrides 原样**(write_world=False),启动即续上传的世界。
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

from ..config import Settings
from ..db import Database
from ..lua import parse_lua_table
from ..models import Instance
from ..parse import parse_id_list_file, parse_ini_file, set_ini_value
from ..ports import (
    AUTH_PORT_RANGE,
    CLUSTER_MASTER_PORT_RANGE,
    MASTER_SERVER_PORT_RANGE,
    SERVER_PORT_RANGE,
    resolve_port,
    used_ports,
)
from ..render import _LIST_FILES, render_id_list
from . import instances as inst_svc

log = logging.getLogger("dst_serverd.importer")


class ImportError_(ValueError):
    pass


# ---------- 解析小工具 ----------
def _get(d: dict, sec: str, key: str, default: str = "") -> str:
    return d.get(sec, {}).get(key, default)


def _b(v: str, default: bool) -> bool:
    v = (v or "").strip().lower()
    return default if v == "" else v == "true"


def _i(v: str, default: int) -> int:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def _extract(archive: Path, dest: Path) -> None:
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)  # zipfile 会清洗成员路径(防越权)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            tf.extractall(dest, filter="data")  # PEP 706:拒绝越权/危险成员
    else:
        raise ImportError_("无法识别的压缩格式(仅支持 .tar.gz/.tgz/.tar 与 .zip)")


def _find_cluster_root(tmp: Path) -> Path:
    candidates = sorted(tmp.rglob("cluster.ini"), key=lambda p: len(p.parts))
    if not candidates:
        raise ImportError_("压缩包内未找到 cluster.ini —— 请上传完整的 Cluster 目录")
    return candidates[0].parent


def _parse_preset(shard_dir: Path, is_master: bool) -> str:
    text = ""
    wf = shard_dir / "worldgenoverride.lua"
    if wf.exists():
        text = wf.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'preset\s*=\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    return inst_svc.MASTER_PRESET if is_master else inst_svc.CAVES_PRESET


def _parse_mods(cluster_root: Path) -> dict[str, dict]:
    """用 Lua 解析器汇总各 Shard modoverrides.lua 的 MOD(含 configuration_options),按 ref 合并。

    返回 {ref: {"enabled": bool, "config": dict}};ref 形如 workshop-<id> 或手动 MOD 目录名。
    """
    merged: dict[str, dict] = {}
    for mo in cluster_root.glob("*/modoverrides.lua"):
        data = parse_lua_table(mo.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            continue
        for ref, val in data.items():
            if not isinstance(ref, str) or not isinstance(val, dict):
                continue
            cfg = val.get("configuration_options") or {}
            if not isinstance(cfg, dict):
                cfg = {}
            entry = merged.setdefault(ref, {"enabled": False, "config": {}})
            entry["enabled"] = entry["enabled"] or bool(val.get("enabled", True))
            entry["config"].update({str(k): v for k, v in cfg.items()})
    return merged


def _finalize_files(
    cdir: Path, master_port: int, resolved: list[tuple[str, int, int, int]],
    access: list, online: bool, token: str, server_language: str,
) -> None:
    """只就地改端口/语言 + 写访问列表 + (在线)写 token,保留其它字段。"""
    ci_path = cdir / "cluster.ini"
    ci_text = ci_path.read_text(encoding="utf-8")
    ci_text = set_ini_value(ci_text, "SHARD", "master_port", master_port)
    ci_text = set_ini_value(ci_text, "NETWORK", "server_language", server_language)
    ci_text = set_ini_value(ci_text, "NETWORK", "cluster_language", server_language)
    ci_path.write_text(ci_text, encoding="utf-8")
    for dir_name, sp, msp, ap in resolved:
        sp_path = cdir / dir_name / "server.ini"
        t = sp_path.read_text(encoding="utf-8")
        t = set_ini_value(t, "NETWORK", "server_port", sp)
        t = set_ini_value(t, "STEAM", "master_server_port", msp)
        t = set_ini_value(t, "STEAM", "authentication_port", ap)
        sp_path.write_text(t, encoding="utf-8")
    for kind, fname in _LIST_FILES.items():
        items = [e for e in access if e.kind == kind]
        target = cdir / fname
        if items:
            target.write_text(render_id_list(items), encoding="utf-8")
        elif target.exists():
            target.unlink()
    if online and token:
        (cdir / "cluster_token.txt").write_text(token.strip() + "\n", encoding="utf-8")


# ---------- 主流程 ----------
def import_archive(
    db: Database, settings: Settings, archive: Path, *,
    name_override: str = "", token_override: str = "",
) -> Instance:
    tmp = Path(tempfile.mkdtemp(prefix="dstd-import-"))
    try:
        _extract(archive, tmp)
        root = _find_cluster_root(tmp)
        ci = parse_ini_file(root / "cluster.ini")

        # 发现 Shard(含 server.ini 的子目录),解析其原始端口
        shard_dirs = sorted(
            p for p in root.iterdir() if p.is_dir() and (p / "server.ini").exists())
        if not shard_dirs:
            raise ImportError_("未找到任何含 server.ini 的 Shard 目录")
        # (dir_name, is_master, preset, server_port, master_server_port, auth_port)
        shards: list[tuple[str, bool, str, int, int, int]] = []
        for sd in shard_dirs:
            si = parse_ini_file(sd / "server.ini")
            is_master = _b(_get(si, "SHARD", "is_master"), sd.name.lower() == "master")
            shards.append((
                sd.name, is_master, _parse_preset(sd, is_master),
                _i(_get(si, "NETWORK", "server_port"), 0),
                _i(_get(si, "STEAM", "master_server_port"), 27016),
                _i(_get(si, "STEAM", "authentication_port"), 8766),
            ))
        if not any(m for _, m, *_ in shards):
            raise ImportError_("缺少 Master Shard(server.ini 中 is_master=true)")
        shards.sort(key=lambda x: (not x[1], x[0]))  # master 在前

        # 元信息
        name = name_override.strip() or _get(ci, "NETWORK", "cluster_name", root.name) or root.name
        token = token_override.strip() or _read_token(root)
        offline = _b(_get(ci, "NETWORK", "offline_cluster"), default=False)
        online = (not offline) and bool(token)
        if not online and not offline:
            log.warning("导入:原为在线服但无 token,降级为离线(可在『配置』补 token 后改回在线)")

        cluster_dir = inst_svc._unique_cluster_dir(db, name)
        cluster_key = _get(ci, "SHARD", "cluster_key") or secrets.token_hex(12)
        game_mode = _get(ci, "GAMEPLAY", "game_mode", "survival")
        if game_mode not in inst_svc.GAME_MODES:
            game_mode = "survival"
        intention = _get(ci, "NETWORK", "cluster_intention", "cooperative")
        if intention not in inst_svc.INTENTIONS:
            intention = "cooperative"
        try:
            server_language = inst_svc.normalize_server_language(
                _get(ci, "NETWORK", "server_language")
                or _get(ci, "NETWORK", "cluster_language")
                or inst_svc.DEFAULT_SERVER_LANGUAGE
            )
        except inst_svc.InstanceError:
            server_language = inst_svc.DEFAULT_SERVER_LANGUAGE

        # 端口:优先沿用存档原值(保住防火墙/端口转发),冲突才另分配
        used_sp = used_ports(db, "server_port")
        used_msp = used_ports(db, "master_server_port")
        used_ap = used_ports(db, "authentication_port")
        used_mp = used_ports(db, "master_port", "server_instances")
        master_port = resolve_port(_i(_get(ci, "SHARD", "master_port"), 10888),
                                   CLUSTER_MASTER_PORT_RANGE, used_mp)

        inst_id = db.execute(
            "INSERT INTO server_instances (name, cluster_dir_name, online, game_mode, pvp, "
            "max_players, max_snapshots, pause_when_empty, cluster_password, cluster_intention, "
            "cluster_description, server_language, cluster_key, master_port, token, tick_rate, "
            "vote_enabled, autosaver_enabled, whitelist_slots, lan_only_cluster, created_at, "
            "desired_status, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'stopped','imported')",
            (
                name, cluster_dir, int(online), game_mode, int(_b(_get(ci, "GAMEPLAY", "pvp"), False)),
                _i(_get(ci, "GAMEPLAY", "max_players"), 6), _i(_get(ci, "MISC", "max_snapshots"), 6),
                int(_b(_get(ci, "GAMEPLAY", "pause_when_empty"), True)),
                _get(ci, "NETWORK", "cluster_password"), intention,
                _get(ci, "NETWORK", "cluster_description"), server_language,
                cluster_key, master_port, token,
                _i(_get(ci, "NETWORK", "tick_rate"), 15),
                int(_b(_get(ci, "GAMEPLAY", "vote_enabled"), True)),
                int(_b(_get(ci, "NETWORK", "autosaver_enabled"), True)),
                _i(_get(ci, "NETWORK", "whitelist_slots"), 0),
                int(_b(_get(ci, "NETWORK", "lan_only_cluster"), False)),
                time.time(),
            ),
        )

        resolved: list[tuple[str, int, int, int]] = []  # dir_name, server, master_server, auth
        for dir_name, is_master, preset, sp0, msp0, ap0 in shards:
            sp = resolve_port(sp0, SERVER_PORT_RANGE, used_sp)
            used_sp.add(sp)
            msp = resolve_port(msp0, MASTER_SERVER_PORT_RANGE, used_msp)
            used_msp.add(msp)
            ap = resolve_port(ap0, AUTH_PORT_RANGE, used_ap)
            used_ap.add(ap)
            resolved.append((dir_name, sp, msp, ap))
            db.execute(
                "INSERT INTO shards (instance_id, role, shard_dir_name, is_master, server_port, "
                "master_server_port, authentication_port, worldgen_preset) VALUES (?,?,?,?,?,?,?,?)",
                (inst_id, "master" if is_master else "secondary", dir_name, int(is_master),
                 sp, msp, ap, preset),
            )

        # 导入访问控制 + MOD(含 configuration_options)到 DB
        for kind, fname in (("admin", "adminlist.txt"), ("whitelist", "whitelist.txt"),
                            ("blocklist", "blocklist.txt")):
            for kid in parse_id_list_file(root / fname):
                db.execute(
                    "INSERT OR IGNORE INTO access_entries (instance_id, kind, klei_id) VALUES (?,?,?)",
                    (inst_id, kind, kid))
        mods = _parse_mods(root)
        for ref, info in mods.items():
            wid, source = (ref[len("workshop-"):], "workshop") \
                if ref.startswith("workshop-") else (ref, "manual")
            db.execute(
                "INSERT OR IGNORE INTO mods (instance_id, workshop_id, enabled, source, config_json) "
                "VALUES (?,?,?,?,?)",
                (inst_id, wid, int(info["enabled"]), source,
                 json.dumps(info["config"], ensure_ascii=False)))

        # 落地:整目录移入 clusters/<新名>/(保留 save/、modoverrides、worldgen/leveldata)
        target = settings.cluster_dir(cluster_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), str(target))

        # 文件落定:只**就地改端口**,保留 [ACCOUNT] encode_user_path、Secondary id、
        # cloud_id、modoverrides、世界数据等所有原字段;语言字段按 DB 规范补齐/对齐。
        _finalize_files(
            target, master_port, resolved, inst_svc.get_access(db, inst_id),
            online, token, server_language)

        inst = inst_svc.get_instance(db, inst_id)
        assert inst is not None
        log.info("📥 导入实例 #%s cluster=%s 端口=%s MOD=%d online=%s(保留原端口与存档)",
                 inst_id, cluster_dir, {d: sp for d, sp, _, _ in resolved}, len(mods), online)
        return inst
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read_token(root: Path) -> str:
    f = root / "cluster_token.txt"
    try:
        return f.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
