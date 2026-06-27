"""SQLite 持久化(见 DESIGN.md 3.3)。

内网部署、单进程后端,用 stdlib sqlite3 + 一把锁即可,无需 ORM。
已去除 users/audit_logs(不做鉴权)。
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS server_instances (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    cluster_dir_name    TEXT NOT NULL UNIQUE,
    online              INTEGER NOT NULL DEFAULT 1,
    game_mode           TEXT NOT NULL DEFAULT 'survival',
    pvp                 INTEGER NOT NULL DEFAULT 0,
    max_players         INTEGER NOT NULL DEFAULT 6,
    max_snapshots       INTEGER NOT NULL DEFAULT 6,
    pause_when_empty    INTEGER NOT NULL DEFAULT 1,
    cluster_password    TEXT NOT NULL DEFAULT '',
    cluster_intention   TEXT NOT NULL DEFAULT 'cooperative',
    cluster_description  TEXT NOT NULL DEFAULT '',
    server_language     TEXT NOT NULL DEFAULT 'zh',
    cluster_language    TEXT NOT NULL DEFAULT 'zh',
    cluster_key         TEXT NOT NULL DEFAULT '',
    master_port         INTEGER NOT NULL DEFAULT 10888,
    token               TEXT NOT NULL DEFAULT '',
    tick_rate           INTEGER NOT NULL DEFAULT 15,
    vote_enabled        INTEGER NOT NULL DEFAULT 1,
    autosaver_enabled   INTEGER NOT NULL DEFAULT 1,
    whitelist_slots     INTEGER NOT NULL DEFAULT 0,
    lan_only_cluster    INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL,
    desired_status      TEXT NOT NULL DEFAULT 'stopped',
    status              TEXT NOT NULL DEFAULT 'created'
);

CREATE TABLE IF NOT EXISTS shards (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id          INTEGER NOT NULL REFERENCES server_instances(id) ON DELETE CASCADE,
    role                 TEXT NOT NULL,                 -- master / secondary
    shard_dir_name       TEXT NOT NULL,                 -- Master / Caves
    is_master            INTEGER NOT NULL DEFAULT 0,
    server_port          INTEGER NOT NULL,
    master_server_port   INTEGER NOT NULL,
    authentication_port  INTEGER NOT NULL,
    worldgen_preset      TEXT NOT NULL DEFAULT 'SURVIVAL_TOGETHER',
    UNIQUE (instance_id, shard_dir_name)
);

CREATE TABLE IF NOT EXISTS mods (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id   INTEGER NOT NULL REFERENCES server_instances(id) ON DELETE CASCADE,
    workshop_id   TEXT NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    enabled       INTEGER NOT NULL DEFAULT 1,
    source        TEXT NOT NULL DEFAULT 'workshop',     -- workshop / manual
    config_json   TEXT NOT NULL DEFAULT '{}',           -- 同 Cluster 各 Shard 默认同配置
    title                  TEXT NOT NULL DEFAULT '',    -- Workshop 标题(检查更新时回填)
    installed_time_updated INTEGER NOT NULL DEFAULT 0,  -- 已安装版本对应的 Workshop 更新时间(基线)
    workshop_time_updated  INTEGER NOT NULL DEFAULT 0,  -- 最近一次查到的 Workshop 更新时间
    last_checked           REAL NOT NULL DEFAULT 0,     -- 上次检查更新时刻
    UNIQUE (instance_id, workshop_id)
);

-- 访问控制:adminlist / whitelist / blocklist 的 KU_/OU_ 条目(见 DESIGN.md 1.3)
CREATE TABLE IF NOT EXISTS access_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id   INTEGER NOT NULL REFERENCES server_instances(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,                        -- admin / whitelist / blocklist
    klei_id       TEXT NOT NULL,                        -- KU_xxxx(在线)/ OU_xxxx(离线)
    note          TEXT NOT NULL DEFAULT '',
    UNIQUE (instance_id, kind, klei_id)
);

CREATE TABLE IF NOT EXISTS backups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id   INTEGER NOT NULL REFERENCES server_instances(id) ON DELETE CASCADE,
    type          TEXT NOT NULL DEFAULT 'file',
    trigger       TEXT NOT NULL DEFAULT 'manual',       -- manual / auto / pre-restore / pre-update
    path          TEXT NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    note          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS proxy_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    enabled     INTEGER NOT NULL DEFAULT 0,
    mode        TEXT NOT NULL DEFAULT 'env',
    scheme      TEXT NOT NULL DEFAULT 'http',
    host        TEXT NOT NULL DEFAULT '',
    port        INTEGER NOT NULL DEFAULT 0,
    username    TEXT NOT NULL DEFAULT '',
    password    TEXT NOT NULL DEFAULT '',
    no_proxy    TEXT NOT NULL DEFAULT '127.0.0.1,localhost',
    updated_at  REAL NOT NULL DEFAULT 0
);

-- 本地通讯录:只要有玩家加入过游戏,系统就自动记住其 昵称↔Klei ID(见 supervisor/manager.py)。
-- 纯本地备忘,方便对好友 ID 做提示/复制;与访问控制(access_entries)无关,全局共享不分实例。
CREATE TABLE IF NOT EXISTS contacts (
    klei_id     TEXT PRIMARY KEY,                  -- KU_xxxx(在线)/ OU_xxxx(离线)
    name        TEXT NOT NULL DEFAULT '',          -- 最近一次见到的昵称
    note        TEXT NOT NULL DEFAULT '',          -- 用户备注(好友标签)
    first_seen  REAL NOT NULL DEFAULT 0,           -- 首次见到时刻
    last_seen   REAL NOT NULL DEFAULT 0,           -- 最近一次加入时刻
    seen_count  INTEGER NOT NULL DEFAULT 0         -- 加入次数
);

-- 全局键值设置(备份策略等)
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# 旧库迁移:为已存在的表补列(IF NOT EXISTS 不会改已建表)
_MIGRATIONS: dict[str, dict[str, str]] = {
    "server_instances": {
        "tick_rate": "INTEGER NOT NULL DEFAULT 15",
        "vote_enabled": "INTEGER NOT NULL DEFAULT 1",
        "autosaver_enabled": "INTEGER NOT NULL DEFAULT 1",
        "whitelist_slots": "INTEGER NOT NULL DEFAULT 0",
        "lan_only_cluster": "INTEGER NOT NULL DEFAULT 0",
        "server_language": "TEXT NOT NULL DEFAULT 'zh'",
        "cluster_language": "TEXT NOT NULL DEFAULT 'zh'",
    },
    "backups": {
        "trigger": "TEXT NOT NULL DEFAULT 'manual'",
    },
    "mods": {
        "title": "TEXT NOT NULL DEFAULT ''",
        "installed_time_updated": "INTEGER NOT NULL DEFAULT 0",
        "workshop_time_updated": "INTEGER NOT NULL DEFAULT 0",
        "last_checked": "REAL NOT NULL DEFAULT 0",
    },
}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.RLock()
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute("INSERT OR IGNORE INTO proxy_config (id) VALUES (1)")
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        for table, cols in _MIGRATIONS.items():
            existing = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            added: set[str] = set()
            for col, ddl in cols.items():
                if col not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                    added.add(col)
            if table == "server_instances" and "cluster_language" in added:
                self._conn.execute(
                    "UPDATE server_instances SET cluster_language = server_language "
                    "WHERE server_language <> ''"
                )

    # ---- 读 ----
    def query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)))

    def query_one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    # ---- 写 ----
    def execute(self, sql: str, params: Iterable = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur.lastrowid if cur.lastrowid is not None else cur.rowcount

    # ---- KV 设置 ----
    def get_kv(self, key: str, default: str = "") -> str:
        r = self.query_one("SELECT value FROM kv WHERE key = ?", (key,))
        return r["value"] if r else default

    def set_kv(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
