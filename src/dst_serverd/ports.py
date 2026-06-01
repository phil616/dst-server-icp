"""端口分配(见 DESIGN.md 1.7 / 3.1)。

约束:
- server_port:同机各 Shard 必须不同。[10998, 11018] 只是自动分配时的默认池
  (该范围内能被 LAN 列表发现),并非硬性限制——用户可自定义为任意 1024–65535 端口。
- master_server_port / authentication_port(Steam 内部)同机各 Shard 必须不同。
- master_port(Shard 间)每 Cluster 一个,且须 ≠ 任一 server_port。
"""

from __future__ import annotations

import socket

from .db import Database

SERVER_PORT_RANGE = range(10998, 11019)
MASTER_SERVER_PORT_RANGE = range(27016, 27117)
AUTH_PORT_RANGE = range(8766, 8867)
CLUSTER_MASTER_PORT_RANGE = range(10880, 10898)


class PortError(RuntimeError):
    pass


def _used(db: Database, column: str, table: str = "shards") -> set[int]:
    rows = db.query(f"SELECT {column} AS p FROM {table}")
    return {r["p"] for r in rows}


def _pick(candidates: range, used: set[int], also_avoid: set[int] = frozenset()) -> int:
    for p in candidates:
        if p not in used and p not in also_avoid:
            return p
    raise PortError(f"端口池耗尽:{candidates}")


def used_ports(db: Database, column: str, table: str = "shards") -> set[int]:
    return _used(db, column, table)


def is_port_free(port: int) -> bool:
    """OS 层预检:尝试绑定该 UDP 端口,成功即空闲、失败即被占用。

    DST 的 server_port / master_server_port / authentication_port 均为 UDP,
    故用 SOCK_DGRAM 探测。不设 SO_REUSEADDR,以便真实反映占用状态
    (含 DB 未跟踪的外部程序或上次崩溃残留的僵尸进程)。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def resolve_port(
    preferred: int | None, candidates: range, used: set[int],
    also_avoid: set[int] = frozenset(),
) -> int:
    """优先沿用 preferred(导入存档时保留原端口/防火墙规则);冲突或缺失才从池中另分配。"""
    if preferred and preferred not in used and preferred not in also_avoid:
        return preferred
    return _pick(candidates, used, also_avoid)


def allocate_shard_ports(db: Database, count: int) -> list[tuple[int, int, int]]:
    """为一个实例的 count 个 Shard 各分配 (server_port, master_server_port, auth_port)。"""
    used_sp = _used(db, "server_port")
    used_msp = _used(db, "master_server_port")
    used_ap = _used(db, "authentication_port")
    result: list[tuple[int, int, int]] = []
    for _ in range(count):
        sp = _pick(SERVER_PORT_RANGE, used_sp)
        used_sp.add(sp)
        msp = _pick(MASTER_SERVER_PORT_RANGE, used_msp)
        used_msp.add(msp)
        ap = _pick(AUTH_PORT_RANGE, used_ap)
        used_ap.add(ap)
        result.append((sp, msp, ap))
    return result


def allocate_master_port(db: Database) -> int:
    used = _used(db, "master_port", table="server_instances")
    server_ports = _used(db, "server_port")
    return _pick(CLUSTER_MASTER_PORT_RANGE, used, also_avoid=server_ports)
