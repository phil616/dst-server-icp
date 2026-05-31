"""配置文件渲染(见 DESIGN.md 2.4 / 3.2)。

把结构化字段渲染成 DST 需要的 cluster.ini / server.ini / *.lua,写回
clusters/<cluster>/ 目录。运行态 Shard 读取这些文件。
"""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .models import AccessEntry, Instance, Mod, Shard


def _bool(v: bool) -> str:
    return "true" if v else "false"


def render_cluster_ini(inst: Instance, has_secondary: bool) -> str:
    lines = [
        "[MISC]",
        f"max_snapshots = {inst.max_snapshots}",
        "console_enabled = true",
        "",
        "[NETWORK]",
        f"cluster_name = {inst.name}",
        f"cluster_description = {inst.cluster_description}",
        f"cluster_password = {inst.cluster_password}",
        f"cluster_intention = {inst.cluster_intention}",
        f"offline_cluster = {_bool(not inst.online)}",
        f"lan_only_cluster = {_bool(inst.lan_only_cluster)}",
        f"tick_rate = {inst.tick_rate}",
        f"whitelist_slots = {inst.whitelist_slots}",
        f"autosaver_enabled = {_bool(inst.autosaver_enabled)}",
        "",
        "[GAMEPLAY]",
        f"game_mode = {inst.game_mode}",
        f"max_players = {inst.max_players}",
        f"pvp = {_bool(inst.pvp)}",
        f"pause_when_empty = {_bool(inst.pause_when_empty)}",
        f"vote_enabled = {_bool(inst.vote_enabled)}",
        "",
        "[SHARD]",
        f"shard_enabled = {_bool(has_secondary)}",
        "bind_ip = 127.0.0.1",
        "master_ip = 127.0.0.1",
        f"master_port = {inst.master_port}",
        f"cluster_key = {inst.cluster_key}",
        "",
    ]
    return "\n".join(lines)


def render_server_ini(shard: Shard, has_secondary: bool) -> str:
    lines = [
        "[NETWORK]",
        f"server_port = {shard.server_port}",
        "",
        "[SHARD]",
        f"is_master = {_bool(shard.is_master)}",
        f"name = {shard.shard_dir_name}",
    ]
    if not shard.is_master:
        lines.append(f"shard_enabled = {_bool(has_secondary)}")
    lines += [
        "",
        "[STEAM]",
        f"master_server_port = {shard.master_server_port}",
        f"authentication_port = {shard.authentication_port}",
        "",
    ]
    return "\n".join(lines)


def render_worldgen(preset: str) -> str:
    return "return {\n" f'  override_enabled = true,\n  preset = "{preset}",\n' "}\n"


def _lua_value(v: object) -> str:
    if isinstance(v, bool):
        return _bool(v)
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{v}"'


def render_modoverrides(mods: list[Mod]) -> str:
    if not mods:
        return "return {}\n"
    out = ["return {"]
    for m in mods:
        out.append(f'  ["{m.ref}"] = {{')
        out.append(f"    enabled = {_bool(m.enabled)},")
        cfg = m.config()
        if cfg:
            out.append("    configuration_options = {")
            for k, v in cfg.items():
                # 用方括号字符串键,兼容中文/空串/下划线开头等非法标识符键
                out.append(f'      ["{k}"] = {_lua_value(v)},')
            out.append("    },")
        out.append("  },")
    out.append("}")
    return "\n".join(out) + "\n"


def render_mods_setup(mods: list[Mod]) -> str:
    lines = [
        f'ServerModSetup("{m.workshop_id}")'
        for m in mods
        if m.source == "workshop"
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def render_id_list(entries: list[AccessEntry]) -> str:
    """adminlist/whitelist/blocklist:每行一个 KU_/OU_ ID。"""
    return "".join(f"{e.klei_id}\n" for e in entries)


_LIST_FILES = {"admin": "adminlist.txt", "whitelist": "whitelist.txt", "blocklist": "blocklist.txt"}


def write_instance_files(
    settings: Settings, inst: Instance, shards: list[Shard], mods: list[Mod],
    access: list[AccessEntry] | None = None, write_world: bool = True,
) -> None:
    """渲染并写回该实例的配置文件到 clusters/<cluster>/。

    write_world=False(导入已有存档时):**只写 cluster.ini / server.ini / 访问列表 / token**,
    保留压缩包里原有的 worldgenoverride.lua / modoverrides.lua / save/(避免覆盖已生成的世界
    与原 MOD 配置)。
    """
    cdir = settings.cluster_dir(inst.cluster_dir_name)
    has_secondary = any(not s.is_master for s in shards)
    cdir.mkdir(parents=True, exist_ok=True)

    _write(cdir / "cluster.ini", render_cluster_ini(inst, has_secondary))
    if inst.online and inst.token:
        _write(cdir / "cluster_token.txt", inst.token.strip() + "\n")

    # 访问控制列表:有条目则写文件,无则删除文件(避免空文件干扰)
    for kind, fname in _LIST_FILES.items():
        items = [e for e in (access or []) if e.kind == kind]
        target = cdir / fname
        if items:
            _write(target, render_id_list(items))
        elif target.exists():
            target.unlink()

    for s in shards:
        sdir = cdir / s.shard_dir_name
        sdir.mkdir(parents=True, exist_ok=True)
        _write(sdir / "server.ini", render_server_ini(s, has_secondary))
        if write_world:
            _write(sdir / "worldgenoverride.lua", render_worldgen(s.worldgen_preset))
            # 列出全部 MOD,停用的写 enabled=false(保留安装与配置,见 DESIGN.md 2.5)
            _write(sdir / "modoverrides.lua", render_modoverrides(mods))

    if write_world:
        # 安装级 MOD 声明(全机并集),写到 server/mods/
        mods_dir = settings.server_dir / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        _write(mods_dir / "dedicated_server_mods_setup.lua", render_mods_setup(mods))


def _write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def mod_setup_path(settings: Settings) -> Path:
    return settings.server_dir / "mods" / "dedicated_server_mods_setup.lua"
