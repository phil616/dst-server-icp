"""存档/快照 自省(见 DESIGN.md 1.9 + 官方 Wiki:save/session/<id>/、快照、回滚)。

DST 每个 Shard 的存档在 <cluster>/<Shard>/save/,内部以 session/<session_id>/ 组织;
每次保存生成一个快照,保留份数由 cluster.ini max_snapshots(默认 6 = 可回滚 5 次)控制。
回滚用控制台命令 c_rollback(n)(经 supervisor 注入,不在此处)。
"""

from __future__ import annotations

from pathlib import Path

from ..config import Settings


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def shard_save_info(settings: Settings, cluster: str, shard_dir: str) -> dict:
    save_root = settings.cluster_dir(cluster) / shard_dir / "save"
    if not save_root.exists():
        return {"shard": shard_dir, "exists": False, "size": 0, "sessions": [], "snapshot_files": 0}

    sessions = []
    session_root = save_root / "session"
    if session_root.exists():
        for sd in sorted(p for p in session_root.iterdir() if p.is_dir()):
            files = [p for p in sd.rglob("*") if p.is_file()]
            sessions.append({
                "session_id": sd.name,
                "files": len(files),
                "size": sum(p.stat().st_size for p in files),
                "mtime": max((p.stat().st_mtime for p in files), default=sd.stat().st_mtime),
            })
    # 快照文件:save 根下形如 *.meta / 编号快照(粗略计数,供参考)
    snapshot_files = sum(1 for p in save_root.glob("*") if p.is_file())
    return {
        "shard": shard_dir,
        "exists": True,
        "size": _dir_size(save_root),
        "sessions": sessions,
        "snapshot_files": snapshot_files,
    }


def instance_save_info(settings: Settings, cluster: str, shard_dirs: list[str]) -> list[dict]:
    return [shard_save_info(settings, cluster, s) for s in shard_dirs]
