"""MOD 更新检查 —— 经 Steam Web API 查 Workshop 的 time_updated 判断是否有新版。

机制(见 Steamworks 文档 ISteamRemoteStorage/GetPublishedFileDetails,公开、免 key):
传入 publishedfileids 批量返回每个 MOD 的 `time_updated`(Unix 秒)与 `title`。
把它与"已安装基线 installed_time_updated"比较:更大 = 有更新。基线在**成功更新后**刷新。
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from urllib.parse import urlencode

from ..activity import install_logger
from ..config import Settings
from ..db import Database
from ..proxy import load_proxy

log = logging.getLogger("dst_serverd.modupdate")

_API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"


def fetch_workshop_details(db: Database, ids: list[str], timeout: float = 15.0) -> dict[str, dict]:
    """批量查 Workshop 详情;返回 {id: {time_updated, title, file_size}}。失败抛异常。"""
    ids = [i for i in dict.fromkeys(ids) if i.isdigit()]
    if not ids:
        return {}
    body = {"itemcount": len(ids)}
    for i, wid in enumerate(ids):
        body[f"publishedfileids[{i}]"] = wid
    data = urlencode(body).encode()

    proxy = load_proxy(db) if db is not None else None
    if proxy and proxy.active:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy.url, "https": proxy.url}))
    else:
        opener = urllib.request.build_opener()
    req = urllib.request.Request(_API, data=data, headers={"User-Agent": "dst-serverd"})
    with opener.open(req, timeout=timeout) as resp:  # noqa: S310 固定可信 URL
        payload = json.load(resp)

    out: dict[str, dict] = {}
    for item in payload.get("response", {}).get("publishedfiledetails", []):
        wid = str(item.get("publishedfileid"))
        if item.get("result") != 1:  # 1 = OK
            continue
        out[wid] = {
            "time_updated": int(item.get("time_updated", 0) or 0),
            "title": item.get("title", "") or "",
            "file_size": int(item.get("file_size", 0) or 0),
        }
    return out


def check_updates(db: Database, instance_id: int) -> list[dict]:
    """查该实例所有 workshop MOD 的最新更新时间,写回 DB。返回每个 MOD 的简报。"""
    rows = db.query(
        "SELECT workshop_id FROM mods WHERE instance_id=? AND source='workshop'", (instance_id,))
    ids = [r["workshop_id"] for r in rows]
    details = fetch_workshop_details(db, ids)
    now = time.time()
    result = []
    for wid in ids:
        d = details.get(wid)
        if d is None:
            db.execute("UPDATE mods SET last_checked=? WHERE instance_id=? AND workshop_id=?",
                       (now, instance_id, wid))
            result.append({"workshop_id": wid, "found": False})
            continue
        db.execute(
            "UPDATE mods SET title=?, workshop_time_updated=?, last_checked=? "
            "WHERE instance_id=? AND workshop_id=?",
            (d["title"], d["time_updated"], now, instance_id, wid))
        result.append({"workshop_id": wid, "found": True, **d})
    log.info("检查更新 instance=%s:%d 个 MOD", instance_id, len(ids))
    return result


def update_mods_job(db: Database, settings: Settings) -> object:
    """后台作业:用 SteamCMD 下载全部 MOD 到 server/mods/(绕开游戏内下载器)→ 对齐基线。

    见 install.py:Klei 论坛/开源镜像验证的做法 —— `-only_update_server_mods` 依赖游戏自带
    steamclient.so 常下载失败;改用 SteamCMD `workshop_download_item 322330 <id>` 并放进
    mods/workshop-<id>/(V1),Shard 以 `-skip_update_server_mods` 加载,稳定可靠。
    """
    from .install import download_mods, fix_steamclient, update_server

    proxy = load_proxy(db)
    # 服务端不在 → 先装(并自动修 steamclient.so)
    if not settings.dst_bin.exists():
        install_logger.info("==> [mods] 服务端本体缺失,先安装/校验…")
        rep = update_server(settings, proxy, validate=True)
        if not getattr(rep, "ok", False):
            install_logger.info("<== [mods] ❌ 服务端安装失败,无法继续(检查 SteamCMD/网络)")
            return rep
    fix_steamclient(settings)

    rows = db.query("SELECT DISTINCT workshop_id FROM mods WHERE source='workshop'")
    ids = [r["workshop_id"] for r in rows]
    res = download_mods(settings, proxy, ids)
    if getattr(res, "ok", False):
        mark_all_installed_current(db, settings)
        install_logger.info("<== [mods] ✅ 全部 MOD 已装入 server/mods/,基线已对齐")
    else:
        install_logger.info("<== [mods] ❌ MOD 更新失败:%s", getattr(res, "error_hint", ""))
    return res


def update_one_mod_job(db: Database, settings: Settings, wid: str) -> object:
    """后台作业:用 SteamCMD 更新单个 MOD(SteamCMD 支持单物品下载)。"""
    from .install import JobResult, download_one_mod, fix_steamclient

    proxy = load_proxy(db)
    fix_steamclient(settings)
    install_logger.info("==> [mods] 更新单个 MOD %s …", wid)
    if download_one_mod(settings, proxy, str(wid)):
        _mark_one_current(db, str(wid))
        install_logger.info("<== [mods] ✅ MOD %s 更新成功", wid)
        return JobResult(f"mod:{wid}", 0, [f"MOD {wid} 已更新"])
    install_logger.info("<== [mods] ❌ MOD %s 更新失败(检查网络/代理 force 模式)", wid)
    return JobResult(f"mod:{wid}", 1, [f"MOD {wid} 更新失败"], f"MOD {wid} 下载失败")


def repair_steam_library_job(db: Database, settings: Settings) -> object:
    """手动修复作业:校验服务端安装 + 覆盖 steamclient.so(修复游戏内下载器)。"""
    from .install import fix_steamclient, update_server

    proxy = load_proxy(db)
    install_logger.info("==> [repair] 校验服务端安装 + 覆盖 steamclient.so(app_update validate)…")
    res = update_server(settings, proxy, validate=True)  # 成功后内部已 fix_steamclient
    if not getattr(res, "ok", False):
        fix_steamclient(settings)
    install_logger.info("<== [repair] %s", "✅ 完成" if getattr(res, "ok", False) else "❌ 失败")
    return res


def _mark_one_current(db: Database, wid: str) -> None:
    try:
        details = fetch_workshop_details(db, [str(wid)])
    except Exception:  # noqa: BLE001
        return
    d = details.get(str(wid))
    if d:
        db.execute(
            "UPDATE mods SET title=?, workshop_time_updated=?, installed_time_updated=?, last_checked=? "
            "WHERE workshop_id=? AND source='workshop'",
            (d["title"], d["time_updated"], d["time_updated"], time.time(), str(wid)))


def mark_all_installed_current(db: Database, settings: Settings) -> int:
    """更新器成功跑完后调用:全局安装已是最新 → 把所有 MOD 的基线设为当前 Workshop 更新时间。

    返回标记的 MOD 行数。会顺带刷新 title/workshop_time_updated/last_checked。
    """
    rows = db.query("SELECT DISTINCT workshop_id FROM mods WHERE source='workshop'")
    ids = [r["workshop_id"] for r in rows]
    if not ids:
        return 0
    try:
        details = fetch_workshop_details(db, ids)
    except Exception:  # noqa: BLE001 网络失败不影响更新本身
        log.warning("更新后刷新基线失败(网络?),跳过")
        return 0
    now = time.time()
    n = 0
    for wid, d in details.items():
        n += db.execute(
            "UPDATE mods SET title=?, workshop_time_updated=?, installed_time_updated=?, last_checked=? "
            "WHERE workshop_id=? AND source='workshop'",
            (d["title"], d["time_updated"], d["time_updated"], now, wid))
    log.info("已将 %d 个 MOD 标记为最新(基线对齐)", len(details))
    return n
