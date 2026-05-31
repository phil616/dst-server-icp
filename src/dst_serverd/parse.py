"""配置解析 —— 把磁盘上的 ini / 列表文件读回结构化形式(见 DESIGN.md 2.4 / 3.2)。

与 render.py(结构化 → 文本)互为反向,用于:查看实际落盘配置、校验、未来导入已有实例。
"""

from __future__ import annotations

import re
from configparser import ConfigParser
from pathlib import Path

from .config import Settings


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """解析 INI 文本为 {section: {key: value}}。DST 的 ini 是标准格式。"""
    cp = ConfigParser()
    cp.optionxform = str  # 保留 key 原始大小写
    cp.read_string(text)
    return {sec: dict(cp.items(sec)) for sec in cp.sections()}


def parse_ini_file(path: Path) -> dict[str, dict[str, str]]:
    try:
        return parse_ini(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def parse_id_list(text: str) -> list[str]:
    """解析 adminlist/whitelist/blocklist:每行一个 KU_/OU_ ID,忽略空行与注释。"""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        out.append(line)
    return out


def parse_id_list_file(path: Path) -> list[str]:
    try:
        return parse_id_list(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def read_cluster_config(settings: Settings, cluster: str) -> dict:
    """读取一个 Cluster 当前**落盘**的全部配置(供前端核对/排错)。"""
    cdir = settings.cluster_dir(cluster)
    shards: dict[str, dict] = {}
    for shard_dir in sorted(p for p in cdir.glob("*") if p.is_dir() and (p / "server.ini").exists()):
        shards[shard_dir.name] = {
            "server_ini": parse_ini_file(shard_dir / "server.ini"),
            "worldgenoverride_lua": _read_text(shard_dir / "worldgenoverride.lua"),
            "modoverrides_lua": _read_text(shard_dir / "modoverrides.lua"),
        }
    return {
        "cluster_ini": parse_ini_file(cdir / "cluster.ini"),
        "has_token": (cdir / "cluster_token.txt").exists(),
        "adminlist": parse_id_list_file(cdir / "adminlist.txt"),
        "whitelist": parse_id_list_file(cdir / "whitelist.txt"),
        "blocklist": parse_id_list_file(cdir / "blocklist.txt"),
        "shards": shards,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def set_ini_value(text: str, section: str, key: str, value: object) -> str:
    """在 INI 文本里**就地**设置 section.key = value(保留其它所有字段/注释/未知项)。

    用于导入存档时只改端口、不动 [ACCOUNT] encode_user_path、Secondary id 等关键字段。
    替换已有键 / 在已有 section 末尾追加 / 整段缺失时新建 section。
    """
    header = f"[{section}]"
    new_line = f"{key} = {value}"
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=", re.IGNORECASE)
    out: list[str] = []
    in_section = False
    found_section = False
    key_set = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not key_set:  # 离开目标段且未设置过 → 在此追加
                out.append(new_line)
                key_set = True
            in_section = stripped == header
            found_section = found_section or in_section
            out.append(line)
            continue
        if in_section and not key_set and key_re.match(line):
            out.append(new_line)
            key_set = True
            continue
        out.append(line)
    if in_section and not key_set:  # 目标段在文件末尾
        out.append(new_line)
        key_set = True
    if not found_section:
        out += ["", header, new_line]
    return "\n".join(out) + "\n"
