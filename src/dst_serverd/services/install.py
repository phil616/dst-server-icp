"""安装/更新 SteamCMD、DST 服务端本体、Workshop MOD(见 DESIGN.md 2.5 / 2.9 / 3.4)。

MOD 下载策略(经 Klei 论坛 / docker-dst-server 等开源实践验证):
**不用游戏内置的 `-only_update_server_mods`**(它依赖游戏自带的 steamclient.so,常报
`ODPF failed entirely` / `Staging/Install library folder not found` 导致下载失败),
改用 **SteamCMD `+workshop_download_item 322330 <id>`(注意是游戏 AppID 322330,不是 343050)**
下载,再拷进 `server/mods/workshop-<id>/`(V1 路径),Shard 以 `-skip_update_server_mods` 加载。
同时把 SteamCMD 的 steamclient.so 覆盖到服务端 lib 目录,修复游戏内下载器(双保险)。

全部子进程都**带超时**,避免卡死阻塞作业队列。叠加代理(env + force proxychains)。
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from ..activity import install_logger
from ..config import Settings
from ..proxy import ProxyConfig, download_env, wrap_argv
from ..render import mod_setup_path

DST_APPID = "343050"        # 专用服务器工具
WORKSHOP_APPID = "322330"   # 游戏本体(Workshop 内容挂在它名下)
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"

# 子进程默认超时(秒)
STEAMCMD_TIMEOUT = 1800     # 装/更服务端(约 2GB)
MOD_TIMEOUT = 600           # 单个 MOD 下载


@dataclass(slots=True)
class JobResult:
    action: str
    returncode: int
    tail: list[str]
    error_hint: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


# ANSI CSI 转义序列(SteamCMD 的颜色码,如 \x1b[0m)与残留控制字符
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # 保留 \t(0x09)与 \n(0x0a)


def _clean(raw: str) -> str:
    """清理子进程输出:去掉 ANSI 颜色码;\\r 进度覆盖只取最终态;去残留控制字符。"""
    seg = raw.rstrip("\n").split("\r")[-1]  # 进度行(\r 覆盖)取最后一段
    return _CTRL_RE.sub("", _ANSI_RE.sub("", seg)).rstrip()


def _emit(line: str) -> None:
    install_logger.info(line)


def _conf_path(settings: Settings) -> Path:
    return settings.run_dir / "proxychains.conf"


def _run(
    settings: Settings, action: str, argv: list[str], *, cwd: Path | None = None,
    env: dict[str, str] | None = None, timeout: float | None = None,
) -> JobResult:
    """跑下载/更新子进程并把输出汇入活动流。**带超时**:超时则杀整个进程组,避免卡死。"""
    proxied = "(经代理)" if env and env.get("http_proxy") else ""
    _emit(f"==> [{action}] 执行{proxied}: {' '.join(argv)}")
    if cwd:
        _emit(f"    工作目录: {cwd}")
    proc = subprocess.Popen(  # noqa: S603 受控参数
        argv, cwd=str(cwd) if cwd else None, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        start_new_session=True,  # 独立进程组,便于超时 killpg
    )
    timed_out = {"v": False}
    timer: threading.Timer | None = None
    if timeout:
        def _kill() -> None:
            timed_out["v"] = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        timer = threading.Timer(timeout, _kill)
        timer.start()

    tail: list[str] = []
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = _clean(raw)
            if not line:
                continue  # 跳过纯 ANSI/空行,减少噪声
            _emit(f"    {line}")
            tail.append(line)
            tail = tail[-300:]
        rc = proc.wait()
    finally:
        if timer:
            timer.cancel()

    if timed_out["v"]:
        _emit(f"<== [{action}] ✗ 超时({timeout:.0f}s)被强制终止")
        return JobResult(action, 124, [*tail, "[超时被终止]"], f"超时({timeout:.0f}s)被终止")
    _emit(f"<== [{action}] {'✓ 成功' if rc == 0 else f'✗ 失败 rc={rc}'}")
    return JobResult(action, rc, tail)


# ---------------- SteamCMD / 服务端 ----------------
def ensure_steamcmd(settings: Settings, proxy: ProxyConfig, *, force: bool = False) -> JobResult:
    steamcmd_sh = settings.steamcmd_dir / "steamcmd.sh"
    if steamcmd_sh.exists() and not force:
        msg = f"SteamCMD 已存在,跳过下载:{steamcmd_sh}"
        _emit(f"==> [steamcmd] {msg}")
        return JobResult("steamcmd:cached", 0, [msg])
    _emit("==> [steamcmd] 开始安装 SteamCMD")
    settings.steamcmd_dir.mkdir(parents=True, exist_ok=True)
    env = download_env(proxy)
    tar = settings.steamcmd_dir / "steamcmd_linux.tar.gz"
    dl = wrap_argv(proxy, ["curl", "-fsSL", "-o", str(tar), STEAMCMD_URL], _conf_path(settings))
    res = _run(settings, "steamcmd:download", dl, env=env, timeout=300)
    if not res.ok:
        return res
    return _run(settings, "steamcmd:extract",
                ["tar", "-xzf", str(tar), "-C", str(settings.steamcmd_dir)], timeout=120)


def update_server(settings: Settings, proxy: ProxyConfig, *, validate: bool = True) -> JobResult:
    steamcmd_sh = settings.steamcmd_dir / "steamcmd.sh"
    if not steamcmd_sh.exists():
        msg = "SteamCMD 未安装,请先执行『装/更 SteamCMD』"
        _emit(f"==> [server:update] {msg}")
        return JobResult("server:update", 127, [msg], msg)
    _emit(f"==> [server:update] 安装/更新 DST 服务端本体(AppID {DST_APPID},validate={validate})")
    settings.server_dir.mkdir(parents=True, exist_ok=True)
    env = download_env(proxy)
    app_arg = f"+app_update {DST_APPID}" + (" validate" if validate else "")
    argv = [
        str(steamcmd_sh),
        "+@ShutdownOnFailedCommand", "1", "+@NoPromptForPassword", "1",
        "+force_install_dir", str(settings.server_dir),
        "+login", "anonymous", *app_arg.split(), "+quit",
    ]
    argv = wrap_argv(proxy, argv, _conf_path(settings))
    res = _run(settings, "server:update", argv, env=env, timeout=STEAMCMD_TIMEOUT)
    if res.ok:
        fix_steamclient(settings)  # 装完顺手修 steamclient.so
    return res


def fix_steamclient(settings: Settings) -> list[str]:
    """把 SteamCMD 的 steamclient.so 覆盖到服务端 lib 目录。

    修复游戏内下载器报 `ODPF failed entirely: 16` / `Staging/Install library folder not found`
    的根因(游戏自带 steamclient.so 损坏/不兼容)。来源:Klei 论坛与 docker-dst-server 实践。
    """
    done: list[str] = []
    mapping = [
        (settings.steamcmd_dir / "linux64" / "steamclient.so", settings.bin_dir / "lib64"),
        (settings.steamcmd_dir / "linux32" / "steamclient.so", settings.server_dir / "bin" / "lib32"),
    ]
    for src, dst_dir in mapping:
        if src.exists():
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_dir / "steamclient.so")
            done.append(str(dst_dir / "steamclient.so"))
    if done:
        _emit(f"==> [steamclient] 已覆盖 steamclient.so:{done}")
    else:
        _emit("==> [steamclient] 未找到 SteamCMD 的 steamclient.so(SteamCMD 尚未运行过?)")
    return done


def check_steam_library(settings: Settings) -> list[str]:
    """轻量预检(SteamCMD/服务端是否就绪)。"""
    issues: list[str] = []
    if not (settings.steamcmd_dir / "steamcmd.sh").exists():
        issues.append("缺少 SteamCMD")
    if not settings.dst_bin.exists():
        issues.append("缺少服务端本体")
    return issues


# ---------------- MOD:用 SteamCMD workshop_download_item ----------------
def _workshop_root(settings: Settings) -> Path:
    return settings.base / "workshop"


def _content_dir(settings: Settings, wid: str) -> Path:
    return _workshop_root(settings) / "steamapps" / "workshop" / "content" / WORKSHOP_APPID / wid


def download_workshop_item(
    settings: Settings, proxy: ProxyConfig, wid: str, timeout: float = MOD_TIMEOUT,
) -> JobResult:
    """用 SteamCMD 下载单个 Workshop 物品(匿名)。内容落到 workshop/steamapps/.../<wid>/。"""
    steamcmd_sh = settings.steamcmd_dir / "steamcmd.sh"
    if not steamcmd_sh.exists():
        return JobResult(f"mod:{wid}", 127, ["SteamCMD 未安装"], "SteamCMD 未安装")
    _workshop_root(settings).mkdir(parents=True, exist_ok=True)
    env = download_env(proxy)
    argv = [
        str(steamcmd_sh),
        "+@ShutdownOnFailedCommand", "1", "+@NoPromptForPassword", "1",
        "+force_install_dir", str(_workshop_root(settings)),
        "+login", "anonymous",
        "+workshop_download_item", WORKSHOP_APPID, str(wid),
        "+quit",
    ]
    argv = wrap_argv(proxy, argv, _conf_path(settings))
    return _run(settings, f"mod:{wid}", argv, env=env, timeout=timeout)


def sync_mod_to_server(settings: Settings, wid: str) -> bool:
    """把下载好的 Workshop 内容拷进 server/mods/workshop-<id>/(V1 路径,服务器据此加载)。"""
    src = _content_dir(settings, wid)
    if not src.is_dir() or not any(src.iterdir()):
        return False
    dst = settings.server_dir / "mods" / f"workshop-{wid}"
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    return (dst / "modinfo.lua").exists() or any(dst.iterdir())


def download_one_mod(settings: Settings, proxy: ProxyConfig, wid: str) -> bool:
    """下载并安装单个 MOD(带一次重试)。返回是否成功落地。"""
    wid = str(wid)
    for attempt in (1, 2):
        r = download_workshop_item(settings, proxy, wid)
        if r.ok and sync_mod_to_server(settings, wid):
            _emit(f"    ✓ MOD {wid} → mods/workshop-{wid}")
            return True
        if attempt == 1:
            _emit(f"    ↻ MOD {wid} 第 1 次失败,重试…")
    _emit(f"    ✗ MOD {wid} 下载/安装失败")
    return False


def download_mods(
    settings: Settings, proxy: ProxyConfig, ids: list[str],
) -> JobResult:
    """用 SteamCMD 逐个下载 MOD 并安装到 server/mods/。"""
    if not (settings.steamcmd_dir / "steamcmd.sh").exists():
        msg = "SteamCMD 未安装,请先『装/更 SteamCMD』"
        return JobResult("mods:update", 127, [msg], msg)
    fix_steamclient(settings)
    ids = list(dict.fromkeys(str(w) for w in ids if str(w).isdigit()))
    if not ids:
        _emit("==> [mods] 没有需要下载的 Workshop MOD")
        return JobResult("mods:update", 0, ["无 MOD"])
    _emit(f"==> [mods] 用 SteamCMD 下载 {len(ids)} 个 MOD(workshop_download_item {WORKSHOP_APPID})")
    settings.server_dir.joinpath("mods").mkdir(parents=True, exist_ok=True)
    failed = [wid for wid in ids if not download_one_mod(settings, proxy, wid)]
    if failed:
        hint = f"以下 MOD 下载失败:{','.join(failed)}(检查网络/代理 force 模式)"
        _emit(f"<== [mods] ✗ {hint}")
        return JobResult("mods:update", 1, [hint], hint)
    _emit(f"<== [mods] ✅ 全部 {len(ids)} 个 MOD 已安装到 server/mods/")
    return JobResult("mods:update", 0, [f"已安装 {len(ids)} 个 MOD"])


def update_mods(settings: Settings, proxy: ProxyConfig) -> JobResult:
    """从 dedicated_server_mods_setup.lua 读取声明的 MOD id,用 SteamCMD 下载安装。"""
    setup = mod_setup_path(settings)
    ids: list[str] = []
    if setup.exists():
        ids = re.findall(r'ServerModSetup\("(\d+)"\)',
                         setup.read_text(encoding="utf-8", errors="replace"))
    return download_mods(settings, proxy, ids)
