"""基础路由:健康检查 + 全局 Shard 进程总览 + APIKey 鉴权探测。

实例 / Shard / MOD / 备份的业务路由见 instances.py;安装更新与代理见 admin.py;
实时日志见 ws.py。鉴权由 main.py 的 api_key_guard 中间件统一处理(见 DESIGN.md 2.8)。
"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Request

import dst_serverd

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": dst_serverd.__version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.system(),
    }


@router.get("/shards")
def list_shards(request: Request) -> list[dict]:
    """所有被托管 Shard 进程的实时状态(跨实例)。"""
    return request.app.state.supervisor.status()


@router.get("/auth/required")
def auth_required(request: Request) -> dict:
    """公开端点(不鉴权):告诉前端本后端是否启用了 APIKey 保护。"""
    return {"required": bool((request.app.state.settings.api_key or "").strip())}


@router.get("/auth/verify")
def auth_verify() -> dict:
    """校验 APIKey:受 api_key_guard 中间件保护。能走到这里即表示 APIKey 有效(或未启用保护)。"""
    return {"ok": True}
