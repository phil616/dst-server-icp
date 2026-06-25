"""领域模型(从 sqlite Row 构造的 dataclass)。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass(slots=True)
class Instance:
    id: int
    name: str
    cluster_dir_name: str
    online: bool
    game_mode: str
    pvp: bool
    max_players: int
    max_snapshots: int
    pause_when_empty: bool
    cluster_password: str
    cluster_intention: str
    cluster_description: str
    server_language: str
    cluster_key: str
    master_port: int
    token: str
    tick_rate: int
    vote_enabled: bool
    autosaver_enabled: bool
    whitelist_slots: int
    lan_only_cluster: bool
    created_at: float
    desired_status: str
    status: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> Instance:
        return cls(
            id=r["id"],
            name=r["name"],
            cluster_dir_name=r["cluster_dir_name"],
            online=bool(r["online"]),
            game_mode=r["game_mode"],
            pvp=bool(r["pvp"]),
            max_players=r["max_players"],
            max_snapshots=r["max_snapshots"],
            pause_when_empty=bool(r["pause_when_empty"]),
            cluster_password=r["cluster_password"],
            cluster_intention=r["cluster_intention"],
            cluster_description=r["cluster_description"],
            server_language=r["server_language"],
            cluster_key=r["cluster_key"],
            master_port=r["master_port"],
            token=r["token"],
            tick_rate=r["tick_rate"],
            vote_enabled=bool(r["vote_enabled"]),
            autosaver_enabled=bool(r["autosaver_enabled"]),
            whitelist_slots=r["whitelist_slots"],
            lan_only_cluster=bool(r["lan_only_cluster"]),
            created_at=r["created_at"],
            desired_status=r["desired_status"],
            status=r["status"],
        )

    def public_dict(self) -> dict:
        # 内网无鉴权:返回真实 token,便于面板查看/编辑。
        # (此前掩码成 "set" 导致面板看不到真值,且保存配置会把 "set" 写回覆盖真 token。)
        d = {k: getattr(self, k) for k in self.__slots__}
        d["has_token"] = bool(self.token)
        return d


@dataclass(slots=True)
class Shard:
    id: int
    instance_id: int
    role: str
    shard_dir_name: str
    is_master: bool
    server_port: int
    master_server_port: int
    authentication_port: int
    worldgen_preset: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> Shard:
        return cls(
            id=r["id"],
            instance_id=r["instance_id"],
            role=r["role"],
            shard_dir_name=r["shard_dir_name"],
            is_master=bool(r["is_master"]),
            server_port=r["server_port"],
            master_server_port=r["master_server_port"],
            authentication_port=r["authentication_port"],
            worldgen_preset=r["worldgen_preset"],
        )

    def public_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


@dataclass(slots=True)
class Mod:
    id: int
    instance_id: int
    workshop_id: str
    name: str
    enabled: bool
    source: str
    config_json: str
    title: str = ""
    installed_time_updated: int = 0
    workshop_time_updated: int = 0
    last_checked: float = 0.0

    @property
    def ref(self) -> str:
        """modoverrides 里引用名:Workshop 用 workshop-<id>,手动 MOD 用目录名。"""
        if self.source == "manual":
            return self.workshop_id
        return f"workshop-{self.workshop_id}"

    @property
    def update_status(self) -> str:
        """latest / outdated / unknown(未建基线)/ unchecked / manual。"""
        if self.source != "workshop":
            return "manual"
        if not self.last_checked:
            return "unchecked"
        if not self.installed_time_updated:
            return "unknown"
        return "outdated" if self.workshop_time_updated > self.installed_time_updated else "latest"

    def config(self) -> dict:
        try:
            return json.loads(self.config_json) or {}
        except json.JSONDecodeError:
            return {}

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> Mod:
        keys = r.keys()
        return cls(
            id=r["id"],
            instance_id=r["instance_id"],
            workshop_id=r["workshop_id"],
            name=r["name"],
            enabled=bool(r["enabled"]),
            source=r["source"],
            config_json=r["config_json"],
            title=r["title"] if "title" in keys else "",
            installed_time_updated=r["installed_time_updated"] if "installed_time_updated" in keys else 0,
            workshop_time_updated=r["workshop_time_updated"] if "workshop_time_updated" in keys else 0,
            last_checked=r["last_checked"] if "last_checked" in keys else 0.0,
        )

    def public_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__slots__ if k != "config_json"}
        d["config"] = self.config()
        d["ref"] = self.ref
        d["update_status"] = self.update_status
        return d


@dataclass(slots=True)
class AccessEntry:
    id: int
    instance_id: int
    kind: str  # admin / whitelist / blocklist
    klei_id: str
    note: str

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> AccessEntry:
        return cls(
            id=r["id"],
            instance_id=r["instance_id"],
            kind=r["kind"],
            klei_id=r["klei_id"],
            note=r["note"],
        )

    def public_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}
