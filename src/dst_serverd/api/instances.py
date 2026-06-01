"""实例 / Shard / MOD / 备份 路由。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..parse import read_cluster_config
from ..services import backups as backup_svc
from ..services import importer as import_svc
from ..services import instances as svc
from ..services import modupdate
from ..services import save as save_svc
from . import deps

router = APIRouter(prefix="/api")


# ---------- 请求体 ----------
class InstanceCreate(BaseModel):
    name: str
    online: bool = True
    token: str = ""
    game_mode: str = "survival"
    pvp: bool = False
    max_players: int = 6
    max_snapshots: int = 6
    pause_when_empty: bool = True
    cluster_password: str = ""
    cluster_intention: str = "cooperative"
    cluster_description: str = ""
    caves: bool = True


class ModCreate(BaseModel):
    workshop_id: str
    name: str = ""
    source: str = "workshop"
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class ModUpdate(BaseModel):
    enabled: bool | None = None
    config: dict | None = None


class BackupCreate(BaseModel):
    note: str = ""


class InstanceUpdate(BaseModel):
    name: str | None = None
    cluster_description: str | None = None
    cluster_password: str | None = None
    cluster_intention: str | None = None
    game_mode: str | None = None
    max_players: int | None = None
    pvp: bool | None = None
    pause_when_empty: bool | None = None
    max_snapshots: int | None = None
    tick_rate: int | None = None
    vote_enabled: bool | None = None
    autosaver_enabled: bool | None = None
    whitelist_slots: int | None = None
    lan_only_cluster: bool | None = None
    online: bool | None = None
    token: str | None = None


class AccessBody(BaseModel):
    kind: str  # admin / whitelist / blocklist
    klei_id: str
    note: str = ""


# ---------- 组装实例视图(配置 + 实时进程状态) ----------
def _instance_view(request: Request, inst) -> dict:
    database = deps.db(request)
    supervisor = deps.sup(request)
    shards = svc.get_shards(database, inst.id)
    live = {s["key"]: s for s in supervisor.status()}
    shard_views = []
    for s in shards:
        key = f"{inst.cluster_dir_name}/{s.shard_dir_name}"
        sv = s.public_dict()
        sv["runtime"] = live.get(key)
        shard_views.append(sv)
    # 每个 MOD 合并"在各 Shard 是否真正加载到游戏"(从日志解析的 loaded_mods)
    mods_out = []
    for m in svc.get_mods(database, inst.id):
        md = m.public_dict()
        loaded: dict[str, dict] = {}
        for s in shards:
            rt = live.get(f"{inst.cluster_dir_name}/{s.shard_dir_name}")
            info = (rt or {}).get("loaded_mods", {}).get(m.ref)
            if info:
                loaded[s.shard_dir_name] = info
        md["loaded"] = loaded
        mods_out.append(md)

    return {
        "instance": inst.public_dict(),
        "shards": shard_views,
        "mods": mods_out,
        "access": [a.public_dict() for a in svc.get_access(database, inst.id)],
    }


# ---------- 实例 CRUD ----------
@router.get("/instances")
def list_instances(request: Request) -> list[dict]:
    return [_instance_view(request, i) for i in svc.list_instances(deps.db(request))]


@router.post("/instances")
def create_instance(body: InstanceCreate, request: Request) -> dict:
    try:
        inst = svc.create_instance(deps.db(request), deps.settings(request), **body.model_dump())
    except svc.InstanceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _instance_view(request, inst)


@router.post("/instances/import")
async def import_instance(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    token: str = Form(""),
) -> dict:
    """从上传的 Cluster 压缩包(.tar.gz/.tgz/.tar/.zip)导入实例,保留其存档世界。"""
    db, settings = deps.db(request), deps.settings(request)
    suffix = Path(file.filename or "upload").suffix or ".tar.gz"
    fd, tmp_name = tempfile.mkstemp(suffix=suffix, prefix="dstd-upload-")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with tmp.open("wb") as out:
            await asyncio.to_thread(shutil.copyfileobj, file.file, out)
        inst = await asyncio.to_thread(
            import_svc.import_archive, db, settings, tmp,
            name_override=name, token_override=token)
    except (import_svc.ImportError_, svc.InstanceError) as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        tmp.unlink(missing_ok=True)
    return _instance_view(request, inst)


@router.get("/instances/{instance_id}")
def get_instance(instance_id: int, request: Request) -> dict:
    return _instance_view(request, deps.require_instance(request, instance_id))


@router.delete("/instances/{instance_id}")
def delete_instance(instance_id: int, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    svc.delete_instance(deps.db(request), deps.settings(request), deps.sup(request), inst)
    return {"deleted": instance_id}


# ---------- 启停 ----------
@router.post("/instances/{instance_id}/start")
def start_instance(instance_id: int, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    svc.start_instance(deps.db(request), deps.settings(request), deps.sup(request), inst)
    return _instance_view(request, deps.require_instance(request, instance_id))


@router.post("/instances/{instance_id}/stop")
def stop_instance(instance_id: int, request: Request, save: bool = True) -> dict:
    inst = deps.require_instance(request, instance_id)
    svc.stop_instance(deps.db(request), deps.sup(request), inst, save=save)
    return _instance_view(request, deps.require_instance(request, instance_id))


@router.post("/instances/{instance_id}/restart")
def restart_instance(instance_id: int, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    svc.stop_instance(deps.db(request), deps.sup(request), inst)
    svc.start_instance(deps.db(request), deps.settings(request), deps.sup(request), inst)
    return _instance_view(request, deps.require_instance(request, instance_id))


# ---------- 控制台命令(发给某 Shard) ----------
class CommandBody(BaseModel):
    command: str


@router.post("/instances/{instance_id}/shards/{shard}/command")
def send_command(instance_id: int, shard: str, body: CommandBody, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    if not deps.sup(request).send(inst.cluster_dir_name, shard, body.command):
        raise HTTPException(409, f"Shard {shard} 不在运行")
    return {"sent": body.command}


# ---------- MOD ----------
@router.get("/mods/search")
def search_mods(request: Request, q: str = "") -> dict:
    """搜索 Workshop MOD(输入 ID 或名称),返回已确认存在的结果供前端点击添加。"""
    q = (q or "").strip()
    if not q:
        return {"results": []}
    try:
        results = modupdate.search_workshop(deps.db(request), q)
    except Exception as exc:  # noqa: BLE001 网络/接口异常
        raise HTTPException(502, f"搜索失败(网络或 Steam):{exc}") from exc
    return {"results": results}


@router.post("/instances/{instance_id}/mods")
def add_mod(instance_id: int, body: ModCreate, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    mod = svc.add_mod(deps.db(request), deps.settings(request), inst, **body.model_dump())
    return mod.public_dict()


@router.patch("/instances/{instance_id}/mods/{workshop_id}")
def update_mod(instance_id: int, workshop_id: str, body: ModUpdate, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    try:
        mod = svc.set_mod(deps.db(request), deps.settings(request), inst, workshop_id,
                          enabled=body.enabled, config=body.config)
    except svc.InstanceError as exc:
        raise HTTPException(404, str(exc)) from exc
    return mod.public_dict()


@router.delete("/instances/{instance_id}/mods/{workshop_id}")
def remove_mod(instance_id: int, workshop_id: str, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    svc.remove_mod(deps.db(request), deps.settings(request), inst, workshop_id)
    return {"removed": workshop_id}


@router.post("/instances/{instance_id}/mods/check-updates")
def check_mod_updates(instance_id: int, request: Request) -> dict:
    """经 Steam Workshop API 检查该实例所有 MOD 是否有新版,回填后返回最新视图。"""
    deps.require_instance(request, instance_id)
    try:
        modupdate.check_updates(deps.db(request), instance_id)
    except Exception as exc:  # noqa: BLE001 网络/接口异常
        raise HTTPException(502, f"检查更新失败(网络或 Steam API):{exc}") from exc
    return _instance_view(request, deps.require_instance(request, instance_id))


@router.post("/instances/{instance_id}/mods/update")
def update_mods(instance_id: int, request: Request) -> dict:
    """触发后台作业:用 SteamCMD 下载全部 MOD 到 server/mods/(绕开游戏内下载器),并对齐基线。"""
    deps.require_instance(request, instance_id)
    settings, db = deps.settings(request), deps.db(request)
    job = request.app.state.jobs.submit(
        "更新全部 MOD", lambda: modupdate.update_mods_job(db, settings))
    return job.public()


@router.post("/instances/{instance_id}/mods/{workshop_id}/update")
def update_one_mod(instance_id: int, workshop_id: str, request: Request) -> dict:
    """触发后台作业:用 SteamCMD 单独更新该 MOD。"""
    deps.require_instance(request, instance_id)
    settings, db = deps.settings(request), deps.db(request)
    job = request.app.state.jobs.submit(
        f"更新 MOD {workshop_id}",
        lambda: modupdate.update_one_mod_job(db, settings, workshop_id))
    return job.public()


# ---------- 备份 ----------
@router.post("/instances/{instance_id}/backups")
def create_backup(instance_id: int, body: BackupCreate, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    return backup_svc.backup_instance(deps.db(request), deps.settings(request), inst, body.note)


@router.get("/instances/{instance_id}/backups")
def list_backups(instance_id: int, request: Request) -> list[dict]:
    deps.require_instance(request, instance_id)
    return backup_svc.list_backups(deps.db(request), instance_id)


# ---------- 配置(房间/元信息/玩法/网络)更新 + 解析 ----------
@router.patch("/instances/{instance_id}")
def update_instance(instance_id: int, body: InstanceUpdate, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    try:
        svc.update_instance(deps.db(request), deps.settings(request), inst,
                            body.model_dump(exclude_unset=True))
    except svc.InstanceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _instance_view(request, deps.require_instance(request, instance_id))


@router.get("/instances/{instance_id}/config/raw")
def get_raw_config(instance_id: int, request: Request) -> dict:
    """读取该实例当前**落盘**的 ini/lua/列表(解析结果),供核对排错。"""
    inst = deps.require_instance(request, instance_id)
    return read_cluster_config(deps.settings(request), inst.cluster_dir_name)


# ---------- 访问控制(adminlist / whitelist / blocklist) ----------
@router.get("/instances/{instance_id}/access")
def list_access(instance_id: int, request: Request, kind: str | None = None) -> list[dict]:
    deps.require_instance(request, instance_id)
    return [a.public_dict() for a in svc.get_access(deps.db(request), instance_id, kind)]


@router.post("/instances/{instance_id}/access")
def add_access(instance_id: int, body: AccessBody, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    try:
        e = svc.add_access(deps.db(request), deps.settings(request), inst,
                           body.kind, body.klei_id, body.note)
    except svc.InstanceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return e.public_dict()


@router.delete("/instances/{instance_id}/access/{kind}/{klei_id}")
def remove_access(instance_id: int, kind: str, klei_id: str, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    svc.remove_access(deps.db(request), deps.settings(request), inst, kind, klei_id)
    return {"removed": {"kind": kind, "klei_id": klei_id}}


# ---------- 存档 / 快照 / 回滚 ----------
@router.get("/instances/{instance_id}/saves")
def list_saves(instance_id: int, request: Request) -> dict:
    inst = deps.require_instance(request, instance_id)
    shard_dirs = [s.shard_dir_name for s in svc.get_shards(deps.db(request), instance_id)]
    return {
        "max_snapshots": inst.max_snapshots,
        "shards": save_svc.instance_save_info(deps.settings(request), inst.cluster_dir_name, shard_dirs),
    }


@router.post("/instances/{instance_id}/shards/{shard}/rollback")
def rollback(instance_id: int, shard: str, request: Request, count: int = 1) -> dict:
    inst = deps.require_instance(request, instance_id)
    if not deps.sup(request).send(inst.cluster_dir_name, shard, f"c_rollback({count})"):
        raise HTTPException(409, f"Shard {shard} 不在运行,无法回滚")
    return {"rolled_back": count, "shard": shard}


# ---------- 备份:还原(先停服→预备份→覆盖→可选重启)/ 删除 / 下载 ----------
@router.post("/backups/{backup_id}/restore")
def restore_backup(backup_id: int, request: Request, restart: bool = False, pre_backup: bool = True) -> dict:
    db, settings, sup = deps.db(request), deps.settings(request), deps.sup(request)
    rec = db.query_one("SELECT * FROM backups WHERE id = ?", (backup_id,))
    if rec is None:
        raise HTTPException(404, f"备份 {backup_id} 不存在")
    inst = svc.get_instance(db, rec["instance_id"])
    if inst is None:
        raise HTTPException(404, "备份对应的实例已不存在")
    svc.stop_instance(db, sup, inst)
    if pre_backup:
        backup_svc.backup_instance(db, settings, inst, note="还原前自动备份", trigger="pre-restore")
    result = backup_svc.restore_backup(db, settings, backup_id)
    if restart:
        svc.start_instance(db, settings, sup, svc.get_instance(db, inst.id))  # type: ignore[arg-type]
        result["restarted"] = True
    return result


@router.delete("/backups/{backup_id}")
def delete_backup(backup_id: int, request: Request) -> dict:
    backup_svc.delete_backup(deps.db(request), backup_id)
    return {"deleted": backup_id}


@router.get("/backups/{backup_id}/download")
def download_backup(backup_id: int, request: Request) -> FileResponse:
    rec = deps.db(request).query_one("SELECT * FROM backups WHERE id = ?", (backup_id,))
    if rec is None:
        raise HTTPException(404, f"备份 {backup_id} 不存在")
    p = Path(rec["path"])
    if not p.exists():
        raise HTTPException(404, "备份文件已丢失")
    return FileResponse(p, filename=p.name, media_type="application/gzip")
