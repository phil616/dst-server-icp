"""安装/更新(后台作业)与 代理配置、作业状态、活动日志 路由(见 DESIGN.md 2.5 / 2.9)。"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..activity import read_tail
from ..proxy import ProxyConfig, load_proxy, save_proxy
from ..services import contacts as contacts_svc
from ..services import install
from ..services import modupdate
from . import deps

router = APIRouter(prefix="/api")


class ProxyBody(BaseModel):
    enabled: bool = False
    mode: str = "env"
    scheme: str = "http"
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    no_proxy: str = "127.0.0.1,localhost"


class ServerUpdateBody(BaseModel):
    validate_files: bool = True  # 装有手动 MOD 时设 false(见 DESIGN.md 3.1#10)


# ---------- 代理 ----------
@router.get("/proxy")
def get_proxy(request: Request) -> dict:
    cfg = load_proxy(deps.db(request))
    d = asdict(cfg)
    d["active"] = cfg.active
    return d


@router.put("/proxy")
def put_proxy(body: ProxyBody, request: Request) -> dict:
    save_proxy(deps.db(request), ProxyConfig(**body.model_dump()))
    return get_proxy(request)


# ---------- 安装/更新:提交后台作业,立即返回 job;输出经活动流(WS)实时可见 ----------
@router.post("/install/steamcmd")
def install_steamcmd(request: Request, force: bool = False) -> dict:
    settings = deps.settings(request)
    proxy = load_proxy(deps.db(request))
    job = request.app.state.jobs.submit(
        "安装/更新 SteamCMD",
        lambda: install.ensure_steamcmd(settings, proxy, force=force),
    )
    return job.public()


@router.post("/install/server")
def install_server(body: ServerUpdateBody, request: Request) -> dict:
    settings = deps.settings(request)
    proxy = load_proxy(deps.db(request))
    job = request.app.state.jobs.submit(
        "安装/更新 DST 服务端本体",
        lambda: install.update_server(settings, proxy, validate=body.validate_files),
    )
    return job.public()


@router.post("/install/mods")
def install_mods(request: Request) -> dict:
    settings, db = deps.settings(request), deps.db(request)
    job = request.app.state.jobs.submit(
        "更新 Workshop MOD（含自动修复）",
        lambda: modupdate.update_mods_job(db, settings),
    )
    return job.public()


@router.post("/install/repair-library")
def repair_library(request: Request) -> dict:
    """手动修复 Steam 库 / 校验服务端安装(解决 Workshop 下载 'library folder not found')。"""
    settings, db = deps.settings(request), deps.db(request)
    job = request.app.state.jobs.submit(
        "修复 Steam 库（校验安装）",
        lambda: modupdate.repair_steam_library_job(db, settings),
    )
    return job.public()


# ---------- 作业状态 ----------
@router.get("/jobs")
def list_jobs(request: Request) -> list[dict]:
    return request.app.state.jobs.list()


@router.get("/jobs/{job_id}")
def get_job(job_id: int, request: Request) -> dict:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"作业 {job_id} 不存在")
    return job


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: int, request: Request) -> dict:
    """中断作业:排队中的直接移除;执行中的强制终止子进程(SIGKILL)。已结束的不可操作。"""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"作业 {job_id} 不存在")
    if not request.app.state.jobs.cancel(job_id):
        raise HTTPException(409, f"作业 {job_id} 当前状态为「{job['status']}」,已结束,无法中断")
    return {"canceled": job_id}


# ---------- 活动日志(系统正在发生什么) ----------
@router.get("/activity")
def activity(request: Request, lines: int = 400) -> dict:
    settings = deps.settings(request)
    return {"lines": read_tail(settings.logs_dir / "activity.log", lines)}


# ---------- 备份策略(全局) ----------
class BackupPolicy(BaseModel):
    auto_enabled: bool = False
    interval_min: int = 360
    retention: int = 10


@router.get("/settings/backup")
def get_backup_policy(request: Request) -> dict:
    db = deps.db(request)
    return {
        "auto_enabled": db.get_kv("backup_auto_enabled", "0") == "1",
        "interval_min": int(db.get_kv("backup_interval_min", "360")),
        "retention": int(db.get_kv("backup_retention", "10")),
    }


@router.put("/settings/backup")
def put_backup_policy(body: BackupPolicy, request: Request) -> dict:
    db = deps.db(request)
    db.set_kv("backup_auto_enabled", "1" if body.auto_enabled else "0")
    db.set_kv("backup_interval_min", str(max(1, body.interval_min)))
    db.set_kv("backup_retention", str(max(1, body.retention)))
    return get_backup_policy(request)


# ---------- 本地通讯录(全局):玩家加入即自动记忆 昵称↔Klei ID ----------
class ContactPatch(BaseModel):
    name: str | None = None
    note: str | None = None


@router.get("/contacts")
def list_contacts(request: Request) -> list[dict]:
    return contacts_svc.list_contacts(deps.db(request))


@router.patch("/contacts/{klei_id}")
def patch_contact(klei_id: str, body: ContactPatch, request: Request) -> list[dict]:
    contacts_svc.update_contact(deps.db(request), klei_id, name=body.name, note=body.note)
    return contacts_svc.list_contacts(deps.db(request))


@router.delete("/contacts/{klei_id}")
def delete_contact(klei_id: str, request: Request) -> dict:
    contacts_svc.delete_contact(deps.db(request), klei_id)
    return {"ok": True}
